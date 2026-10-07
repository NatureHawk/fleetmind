"""Controlled algorithm experiments.

For every repetition ``r`` the runner derives one seed and executes the scenario once per
algorithm. Within a repetition all runs share the same seed, so they start from the same
city, the same fleet, the same order arrival stream and the same incident timeline; the
only independent variable is the path-planning algorithm. Each run records fingerprints of
those inputs and the runner verifies they are identical before reporting results.

Every metric comes from a real headless execution of :class:`SimulationEngine`.
``run_single`` is a top-level function so it can execute in a worker process.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.simulation.engine import SimulationEngine
from app.simulation.scenarios import ScenarioConfig

REPETITION_SEED_STRIDE = 1009

# Metrics aggregated across repetitions (mean / std / min / max).
METRIC_KEYS = (
    "deliveries_completed", "deliveries_failed", "orders_created", "completion_rate", "on_time_rate",
    "average_delivery_time", "p90_delivery_time", "avg_route_cost", "avg_hops", "nodes_explored",
    "avg_nodes_explored", "max_nodes_explored", "searches", "avg_planning_ms", "planning_ms_total",
    "plan_success_rate", "energy_consumed_kwh", "energy_per_delivery_wh", "distance_km", "replans",
    "robot_utilization", "battery_depletions", "charge_sessions", "preemptions",
)


def seed_for(base_seed: int, repetition: int) -> int:
    return base_seed + repetition * REPETITION_SEED_STRIDE


def run_single(payload: dict[str, Any]) -> dict[str, Any]:
    scenario = ScenarioConfig(**payload["scenario"])
    algorithm = payload["algorithm"]
    repetition = int(payload.get("repetition", 0))
    seed = seed_for(scenario.seed, repetition)
    duration = float(payload.get("duration_s", scenario.duration_s))
    cfg = scenario.model_copy(update={"algorithm": algorithm, "seed": seed, "demo": False, "duration_s": duration})

    t0 = perf_counter()
    engine = SimulationEngine(cfg)
    engine.run_until(duration)
    wall = perf_counter() - t0

    g = engine.metrics.global_summary(engine)
    a = engine.metrics.algorithm_summary().get(algorithm, {})
    metrics = {
        "deliveries_completed": g["orders_delivered"],
        "deliveries_failed": g["orders_failed"],
        "orders_created": g["orders_created"],
        "completion_rate": g["completion_rate"],
        "on_time_rate": g["on_time_rate"],
        "average_delivery_time": g["avg_delivery_time"],
        "p90_delivery_time": g["p90_delivery_time"],
        "avg_route_cost": a.get("avg_route_cost"),
        "avg_hops": a.get("avg_hops"),
        "nodes_explored": a.get("nodes_explored", 0),
        "avg_nodes_explored": a.get("avg_nodes_explored"),
        "max_nodes_explored": a.get("max_nodes_explored"),
        "searches": a.get("searches", 0),
        "avg_planning_ms": a.get("avg_planning_ms"),
        "planning_ms_total": a.get("planning_ms_total"),
        "plan_success_rate": a.get("success_rate"),
        "energy_consumed_kwh": g["total_energy_kwh"],
        "energy_per_delivery_wh": g["energy_per_delivery_wh"],
        "distance_km": g["total_distance_km"],
        "replans": g["replans"],
        "robot_utilization": g["robot_utilization"],
        "battery_depletions": g["battery_depletions"],
        "charge_sessions": g["charge_sessions"],
        "preemptions": g["preemptions"],
    }
    samples = engine.metrics.samples
    step = max(1, len(samples) // 60)
    return {
        "algorithm": algorithm,
        "repetition": repetition,
        "seed": seed,
        "duration_s": duration,
        "wall_time_s": round(wall, 3),
        "fingerprints": engine.fingerprints,
        "metrics": metrics,
        "timeseries": [{"t": s["t"], "delivered": s["delivered"], "energy_wh": s["energy_wh"],
                        "replans": s["replans"], "open": s["open"], "nodes_explored": s["nodes_explored"]}
                       for s in samples[::step]],
        "robots": [{"id": r["id"], "utilization": r["utilization"], "orders_completed": r["orders_completed"],
                    "distance_km": r["distance_km"], "energy_wh": r["energy_wh"]}
                   for r in engine.metrics.robot_metrics(engine)],
        "summary": g,
    }


def _stats(values: list[float]) -> dict[str, float | None]:
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": round(statistics.fmean(vals), 4),
        "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "n": len(vals),
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_alg: dict[str, list[dict]] = {}
    for r in results:
        by_alg.setdefault(r["algorithm"], []).append(r)
    return {alg: {key: _stats([run["metrics"].get(key) for run in runs]) for key in METRIC_KEYS}
            for alg, runs in by_alg.items()}


def fairness_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_rep: dict[int, list[dict]] = {}
    for r in results:
        by_rep.setdefault(r["repetition"], []).append(r)
    reps = []
    all_ok = True
    for rep, runs in sorted(by_rep.items()):
        prints = {json_key: {run["fingerprints"][json_key] for run in runs} for json_key in runs[0]["fingerprints"]}
        identical = all(len(v) == 1 for v in prints.values())
        all_ok &= identical
        reps.append({"repetition": rep, "seed": runs[0]["seed"], "identical": identical,
                     "fingerprints": {k: sorted(v) for k, v in prints.items()}})
    return {"identical_conditions": all_ok, "repetitions": reps}


def run_experiment(scenario: ScenarioConfig, algorithms: list[str], repetitions: int, duration_s: float,
                   progress: Callable[[int, int, dict], None] | None = None) -> dict[str, Any]:
    """Sequential in-process runner (used by tests and the CLI; the API uses worker processes)."""
    payloads = build_payloads(scenario, algorithms, repetitions, duration_s)
    results = []
    for i, payload in enumerate(payloads, start=1):
        result = run_single(payload)
        results.append(result)
        if progress:
            progress(i, len(payloads), result)
    return {"results": results, "aggregates": aggregate(results), "fairness": fairness_report(results)}


def build_payloads(scenario: ScenarioConfig, algorithms: list[str], repetitions: int,
                   duration_s: float) -> list[dict[str, Any]]:
    base = scenario.model_dump()
    return [{"scenario": base, "algorithm": alg, "repetition": rep, "duration_s": duration_s}
            for rep in range(repetitions) for alg in algorithms]
