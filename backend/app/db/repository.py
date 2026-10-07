"""Persistence operations (Repository pattern).

All methods are synchronous and short; the async services call them through
``asyncio.to_thread`` so database I/O never blocks the simulation loop.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, desc, func, select

from app.db.session import Database
from app.db.tables import (
    AlgorithmResultRow,
    EnvironmentRow,
    ExperimentRow,
    MetricSampleRow,
    NodeRow,
    OrderRow,
    RoadRow,
    RobotRow,
    SimulationEventRow,
    SimulationRunRow,
    utcnow,
)

if TYPE_CHECKING:
    from app.simulation.engine import SimulationEngine
    from app.simulation.timeline import TimelineEntry


def new_id() -> str:
    return uuid.uuid4().hex


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # Environments ------------------------------------------------------------------------
    def ensure_environment(self, engine: SimulationEngine) -> int:
        env = engine.env
        fp = env.fingerprint()
        with self.db.session_factory() as s:
            existing = s.scalar(select(EnvironmentRow.id).where(EnvironmentRow.fingerprint == fp))
            if existing is not None:
                return existing
            row = EnvironmentRow(seed=env.seed, fingerprint=fp, node_count=len(env.nodes), road_count=len(env.roads),
                                 width=env.width, height=env.height)
            s.add(row)
            s.flush()
            s.add_all([NodeRow(environment_id=row.id, node_id=n.id, name=n.name, kind=n.kind.value,
                               zone=n.zone.value, x=n.x, y=n.y) for n in env.nodes])
            s.add_all([RoadRow(environment_id=row.id, road_id=r.id, source=r.a, destination=r.b, distance=r.length,
                               road_class=r.road_class.value, travel_time=round(r.travel_time, 3),
                               energy_cost=round(r.energy_cost, 3)) for r in env.roads])
            s.commit()
            return row.id

    # Runs ----------------------------------------------------------------------------------
    def create_run(self, engine: SimulationEngine, mode: str, experiment_id: str | None = None,
                   run_id: str | None = None) -> str:
        env_id = self.ensure_environment(engine)
        cfg = engine.config
        rid = run_id or new_id()
        with self.db.session_factory() as s:
            s.add(SimulationRunRow(id=rid, mode=mode, scenario_key=cfg.key, scenario_name=cfg.name, seed=cfg.seed,
                                   algorithm=engine.routes.algorithm, heuristic=engine.routes.heuristic,
                                   config=cfg.model_dump(), fingerprints=engine.fingerprints, environment_id=env_id,
                                   experiment_id=experiment_id, status="running"))
            s.commit()
        return rid

    def add_events(self, run_id: str, entries: list[TimelineEntry]) -> None:
        if not entries:
            return
        with self.db.session_factory() as s:
            s.add_all([SimulationEventRow(run_id=run_id, seq=e.seq, sim_time=e.t, category=e.category.value,
                                          kind=e.kind, severity=e.severity.value, message=e.message,
                                          robot_id=e.robot_id, order_id=e.order_id, road_id=e.road_id,
                                          node_id=e.node_id, data=e.data or None) for e in entries])
            s.commit()

    def add_metric_samples(self, run_id: str, samples: list[dict]) -> None:
        if not samples:
            return
        with self.db.session_factory() as s:
            s.add_all([MetricSampleRow(run_id=run_id, sim_time=x["t"], data=x) for x in samples])
            s.commit()

    def finish_run(self, run_id: str, engine: SimulationEngine, status: str = "completed") -> None:
        summary = engine.metrics.global_summary(engine)
        summary["algorithms"] = engine.metrics.algorithm_summary()
        with self.db.session_factory() as s:
            run = s.get(SimulationRunRow, run_id)
            if run is None:
                return
            run.status = status
            run.sim_time = engine.now
            run.summary = summary
            run.algorithm = engine.routes.algorithm
            run.ended_at = utcnow()
            s.execute(delete(RobotRow).where(RobotRow.run_id == run_id))
            s.execute(delete(OrderRow).where(OrderRow.run_id == run_id))
            for r in engine.fleet.robots:
                s.add(RobotRow(run_id=run_id, robot_id=r.id, model=r.model.name, capacity=r.capacity,
                               max_battery_wh=r.max_battery_wh, final_battery_pct=round(r.battery_pct, 2),
                               orders_completed=r.orders_completed, distance_km=round(r.total_distance / 1000, 4),
                               energy_wh=round(r.energy_consumed, 2), utilization=round(r.utilization, 4),
                               replans=r.replans, charge_sessions=r.charge_sessions, depletions=r.depletions))
            for o in engine.orders.all():
                s.add(OrderRow(run_id=run_id, order_id=o.id, source=o.source, destination=o.destination,
                               priority=o.priority.label, status=o.status.value, created_time=o.created_at,
                               deadline=o.deadline, assigned_robot=o.assigned_robot, assigned_time=o.assigned_at,
                               picked_up_time=o.picked_up_at, delivered_time=o.delivered_at,
                               failure_reason=o.failure_reason))
            s.commit()

    def list_runs(self, limit: int = 30, mode: str | None = None) -> list[dict]:
        with self.db.session_factory() as s:
            q = select(SimulationRunRow).order_by(desc(SimulationRunRow.started_at)).limit(limit)
            if mode:
                q = q.where(SimulationRunRow.mode == mode)
            counts = dict(s.execute(select(SimulationEventRow.run_id, func.count())
                                    .group_by(SimulationEventRow.run_id)).all())
            return [self._run_dict(r, counts.get(r.id, 0)) for r in s.scalars(q)]

    def get_run(self, run_id: str) -> dict | None:
        with self.db.session_factory() as s:
            r = s.get(SimulationRunRow, run_id)
            if r is None:
                return None
            data = self._run_dict(r, s.scalar(select(func.count()).where(SimulationEventRow.run_id == run_id)) or 0)
            data["metrics"] = [m.data for m in s.scalars(select(MetricSampleRow).where(MetricSampleRow.run_id == run_id)
                                                          .order_by(MetricSampleRow.sim_time))]
            return data

    def run_events(self, run_id: str, limit: int = 500, kind: str | None = None) -> list[dict]:
        with self.db.session_factory() as s:
            q = select(SimulationEventRow).where(SimulationEventRow.run_id == run_id)
            if kind:
                q = q.where(SimulationEventRow.kind == kind)
            q = q.order_by(SimulationEventRow.seq).limit(limit)
            return [{"seq": e.seq, "t": e.sim_time, "category": e.category, "kind": e.kind, "severity": e.severity,
                     "message": e.message, "robot_id": e.robot_id, "order_id": e.order_id, "road_id": e.road_id,
                     "node_id": e.node_id, "data": e.data or {}} for e in s.scalars(q)]

    @staticmethod
    def _run_dict(r: SimulationRunRow, events: int) -> dict:
        return {"id": r.id, "mode": r.mode, "scenario_key": r.scenario_key, "scenario_name": r.scenario_name,
                "seed": r.seed, "algorithm": r.algorithm, "heuristic": r.heuristic, "status": r.status,
                "sim_time": r.sim_time, "summary": r.summary, "fingerprints": r.fingerprints,
                "experiment_id": r.experiment_id, "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None, "event_count": events}

    # Experiments ---------------------------------------------------------------------------
    def create_experiment(self, exp_id: str, name: str, scenario: dict, algorithms: list[str], repetitions: int,
                          duration_s: float) -> None:
        with self.db.session_factory() as s:
            s.add(ExperimentRow(id=exp_id, name=name, scenario_key=scenario["key"], seed=scenario["seed"],
                                algorithms=algorithms, repetitions=repetitions, duration_s=duration_s, config=scenario,
                                status="running", progress=0.0))
            s.commit()

    def update_experiment_progress(self, exp_id: str, progress: float) -> None:
        with self.db.session_factory() as s:
            row = s.get(ExperimentRow, exp_id)
            if row is not None:
                row.progress = progress
                s.commit()

    def complete_experiment(self, exp_id: str, results: list[dict], aggregates: dict, fairness: dict,
                            env_engine: SimulationEngine | None = None) -> None:
        env_id = self.ensure_environment(env_engine) if env_engine is not None else None
        with self.db.session_factory() as s:
            row = s.get(ExperimentRow, exp_id)
            if row is None:
                return
            for res in results:
                run_id = new_id()
                cfg = dict(row.config, algorithm=res["algorithm"], seed=res["seed"])
                s.add(SimulationRunRow(id=run_id, mode="experiment", scenario_key=row.scenario_key,
                                       scenario_name=row.config.get("name", row.scenario_key), seed=res["seed"],
                                       algorithm=res["algorithm"], heuristic=row.config.get("heuristic", "euclidean"),
                                       config=cfg, fingerprints=res["fingerprints"],
                                       environment_id=env_id if res["repetition"] == 0 else None,
                                       experiment_id=exp_id, status="completed", sim_time=res["duration_s"],
                                       summary=res["summary"], ended_at=utcnow()))
                s.flush()
                m = res["metrics"]
                s.add(AlgorithmResultRow(
                    experiment_id=exp_id, run_id=run_id, algorithm=res["algorithm"], repetition=res["repetition"],
                    seed=res["seed"], deliveries_completed=m["deliveries_completed"],
                    deliveries_failed=m["deliveries_failed"], average_delivery_time=m["average_delivery_time"],
                    avg_route_cost=m["avg_route_cost"], nodes_explored=m["nodes_explored"] or 0,
                    avg_nodes_explored=m["avg_nodes_explored"], avg_planning_ms=m["avg_planning_ms"],
                    energy_consumed_kwh=m["energy_consumed_kwh"], distance_km=m["distance_km"], replans=m["replans"],
                    robot_utilization=m["robot_utilization"], wall_time_s=res["wall_time_s"], metrics=m,
                    timeseries=res.get("timeseries")))
            row.status = "completed"
            row.progress = 1.0
            row.aggregates = aggregates
            row.fairness = fairness
            row.completed_at = utcnow()
            s.commit()

    def fail_experiment(self, exp_id: str, error: str) -> None:
        with self.db.session_factory() as s:
            row = s.get(ExperimentRow, exp_id)
            if row is not None:
                row.status = "failed"
                row.error = error[:2000]
                row.completed_at = utcnow()
                s.commit()

    def list_experiments(self, limit: int = 50) -> list[dict]:
        with self.db.session_factory() as s:
            rows = s.scalars(select(ExperimentRow).order_by(desc(ExperimentRow.created_at)).limit(limit))
            return [self._experiment_dict(r, include_results=False, session=s) for r in rows]

    def get_experiment(self, exp_id: str) -> dict | None:
        with self.db.session_factory() as s:
            row = s.get(ExperimentRow, exp_id)
            return None if row is None else self._experiment_dict(row, include_results=True, session=s)

    def delete_experiment(self, exp_id: str) -> bool:
        with self.db.session_factory() as s:
            row = s.get(ExperimentRow, exp_id)
            if row is None:
                return False
            s.execute(delete(AlgorithmResultRow).where(AlgorithmResultRow.experiment_id == exp_id))
            s.execute(delete(SimulationRunRow).where(SimulationRunRow.experiment_id == exp_id))
            s.delete(row)
            s.commit()
            return True

    @staticmethod
    def _experiment_dict(r: ExperimentRow, include_results: bool, session: Any) -> dict:
        data: dict[str, Any] = {
            "id": r.id, "name": r.name, "scenario_key": r.scenario_key, "seed": r.seed, "algorithms": r.algorithms,
            "repetitions": r.repetitions, "duration_s": r.duration_s, "status": r.status, "progress": r.progress,
            "aggregates": r.aggregates, "fairness": r.fairness, "error": r.error, "config": r.config,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        if include_results:
            rows = session.scalars(select(AlgorithmResultRow).where(AlgorithmResultRow.experiment_id == r.id)
                                   .order_by(AlgorithmResultRow.repetition, AlgorithmResultRow.id))
            data["results"] = [{"algorithm": x.algorithm, "repetition": x.repetition, "seed": x.seed,
                                "run_id": x.run_id, "wall_time_s": x.wall_time_s, "metrics": x.metrics,
                                "timeseries": x.timeseries or []} for x in rows]
        return data
