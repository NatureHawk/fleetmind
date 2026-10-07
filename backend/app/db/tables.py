"""ORM tables.

Design notes
------------
* The city is stored once per (seed, generator) as an *environment* with its nodes and
  roads; runs reference it instead of duplicating the map.
* Live state is never written per frame. A run persists its decision timeline (in batches),
  periodic metric samples, and final robot/order records when it ends.
* Experiments store one ``algorithm_results`` row per (algorithm, repetition) with the key
  metrics as typed columns (for querying) plus the full metric set as JSON.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EnvironmentRow(Base):
    __tablename__ = "environments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    road_count: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NodeRow(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("environment_id", "node_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    zone: Mapped[str] = mapped_column(String(16), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)


class RoadRow(Base):
    __tablename__ = "roads"
    __table_args__ = (UniqueConstraint("environment_id", "road_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    road_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[int] = mapped_column(Integer, nullable=False)
    destination: Mapped[int] = mapped_column(Integer, nullable=False)
    distance: Mapped[float] = mapped_column(Float, nullable=False)
    road_class: Mapped[str] = mapped_column(String(16), nullable=False)
    travel_time: Mapped[float] = mapped_column(Float, nullable=False)
    energy_cost: Mapped[float] = mapped_column(Float, nullable=False)


class ExperimentRow(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scenario_key: Mapped[str] = mapped_column(String(40), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithms: Mapped[list] = mapped_column(JSONType, nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    aggregates: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    fairness: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # live | experiment
    scenario_key: Mapped[str] = mapped_column(String(40), nullable=False)
    scenario_name: Mapped[str] = mapped_column(String(120), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    heuristic: Mapped[str] = mapped_column(String(16), nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False)
    fingerprints: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id"), nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"),
                                                      nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    sim_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SimulationEventRow(Base):
    __tablename__ = "simulation_events"
    __table_args__ = (Index("ix_simulation_events_run_seq", "run_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    sim_time: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    robot_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    road_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class RobotRow(Base):
    __tablename__ = "robots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    robot_id: Mapped[str] = mapped_column(String(12), nullable=False)
    model: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    max_battery_wh: Mapped[float] = mapped_column(Float, nullable=False)
    final_battery_pct: Mapped[float] = mapped_column(Float, nullable=False)
    orders_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    energy_wh: Mapped[float] = mapped_column(Float, nullable=False)
    utilization: Mapped[float] = mapped_column(Float, nullable=False)
    replans: Mapped[int] = mapped_column(Integer, nullable=False)
    charge_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    depletions: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderRow(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[int] = mapped_column(Integer, nullable=False)
    destination: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_time: Mapped[float] = mapped_column(Float, nullable=False)
    deadline: Mapped[float] = mapped_column(Float, nullable=False)
    assigned_robot: Mapped[str | None] = mapped_column(String(12), nullable=True)
    assigned_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked_up_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivered_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MetricSampleRow(Base):
    __tablename__ = "metrics"
    __table_args__ = (Index("ix_metrics_run_time", "run_id", "sim_time"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False)
    sim_time: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)


class AlgorithmResultRow(Base):
    __tablename__ = "algorithm_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_runs.id", ondelete="SET NULL"), nullable=True)
    algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    repetition: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    deliveries_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    deliveries_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    average_delivery_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_route_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    nodes_explored: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_nodes_explored: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_planning_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_consumed_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    replans: Mapped[int] = mapped_column(Integer, nullable=False)
    robot_utilization: Mapped[float | None] = mapped_column(Float, nullable=True)
    wall_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONType, nullable=False)
    timeseries: Mapped[list | None] = mapped_column(JSONType, nullable=True)
