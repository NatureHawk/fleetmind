# Experiments

## Question

*Holding everything else constant, how does the choice of path-planning algorithm change search
effort, route quality and fleet-level outcomes?*

## Design

* **Independent variable:** the planner (BFS, DFS, Greedy, Dijkstra, A*).
* **Controlled:** city graph, fleet (models, positions, batteries), order arrivals, incident
  timeline, allocation policy, durations — all derived from the seed.
* **Repetitions:** seeds `base + r × 1009` for r = 0…R−1. Each algorithm runs once per seed.
* **Verification:** each run reports four fingerprints — graph (node coordinates/kinds, roads,
  initial traffic), fleet (ids, models, start nodes, batteries, speeds, capacities), orders (the
  order RNG's initial state) and events (the incident schedule). The runner checks they are
  identical across algorithms within each repetition and reports `identical_conditions`.

Because incidents are scheduled from the seed rather than reacting to agents, an algorithm cannot
"avoid" an incident by being elsewhere — every run faces the same closures at the same times.
The guided demo's director reacts to agents and is excluded from experiments.

## Running

UI: **Experiments** → choose scenario, seed, duration, repetitions, algorithms → *Run*.

API:

```bash
curl -X POST localhost:8000/api/experiments/run -H 'content-type: application/json' \
  -d '{"scenario":"road_closure","seed":42173,"repetitions":3,"duration_s":1800}'
curl localhost:8000/api/experiments/<id>
```

Python (sequential, no server):

```python
from app.metrics.experiment_runner import run_experiment
from app.simulation.scenarios import get_scenario
out = run_experiment(get_scenario("baseline", seed=42173), ["astar", "dijkstra"], repetitions=3, duration_s=1800)
out["fairness"]["identical_conditions"], out["aggregates"]["astar"]["avg_nodes_explored"]
```

## Metrics

| Metric | Definition |
|---|---|
| Deliveries completed / failed | Orders delivered / failed (parcel lost to a fault or depletion, or expired unassigned) within the horizon |
| Completion rate | delivered ÷ (delivered + failed) |
| On-time rate | delivered before deadline ÷ delivered |
| Average delivery time | mean(delivered_at − created_at) |
| Path cost | mean planned travel time (s) of successful searches |
| Nodes explored / search | mean expansions per *executed* search (cache hits excluded) |
| Time / search | mean wall-clock search time (ms), measured in the worker process |
| Energy, Wh / delivery | total energy drawn; energy ÷ deliveries |
| Replans | route invalidations + congestion reroutes |
| Utilisation | time with assigned work ÷ (working + idle + charging) time, averaged over robots |
| Strandings | robots that ran out of battery |

Aggregates report mean, standard deviation, min, max and n across repetitions.

## Reference results

See the README's [Results](../README.md#results-measured) section (seed 42173, 3 repetitions ×
30 simulated minutes, baseline and road-closure scenarios).

## Threats to validity

* Wall-clock timings depend on machine load; use node counts for effort comparisons.
* Fleet outcomes depend on the allocation policy and parameters as well as the planner; the
  allocator is identical across runs and deliberately planner-independent.
* 30-minute horizons include warm-up; runs end with orders in progress.
* Small numbers of repetitions give wide confidence intervals for fleet metrics; search
  metrics (hundreds of searches per run) are much tighter.
