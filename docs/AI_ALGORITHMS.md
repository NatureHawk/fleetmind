# AI algorithms

## The search problem

* **State** — a node of the road graph (warehouse, customer, charger, intersection).
* **Actions** — drive along an open road (closed roads known to the fleet are removed from
  `WorldModel.neighbors`).
* **Step cost** — travel time in seconds for a reference robot:

  ```
  cost(road) = length / (8 m/s × class_factor) × traffic_factor
  class_factor:   arterial 1.35 · collector 1.0 · local 0.8
  traffic_factor: low 1.0 · moderate 1.5 · high 2.3 · jammed 3.6
  ```

* **Goal test** — the node equals the next stop (pickup, drop-off or charger). All five planners
  test the goal when a node is *expanded*, so `nodes_explored` is comparable across them.

Every planner implements `PathPlanner.find_path(graph, start, goal, trace=False)` and returns a
`SearchResult` with `path`, `cost`, `success`, `nodes_explored` (expansions),
`nodes_generated` (frontier insertions), `max_frontier` and `elapsed_ms`. With `trace=True` it
also records every expansion and the nodes it added — the Algorithm Explorer animates this.
Neighbours are visited in ascending node id, so every algorithm is deterministic.

No planner imports another; `tests/unit/test_planners.py::test_algorithms_are_independent_modules`
enforces it.

---

## Breadth-First Search — `planning/bfs.py`

**What it does.** Expands nodes in order of distance *in roads* from the start using a FIFO
queue; marks nodes visited when first discovered.

**Why it exists.** The canonical uninformed, complete search; the baseline for "shortest" in an
unweighted sense.

**Complexity.** O(V + E) time, O(V) space.

**When it performs well.** Unweighted graphs or graphs whose edges cost about the same.

**In FleetMind.** Finds the route with the fewest road segments. It ignores that arterials are
faster and that some roads are jammed, so its routes cost ~14 % more travel time than optimal
in the baseline scenario and it expands almost the whole graph for distant goals.

## Depth-First Search — `planning/dfs.py`

**What it does.** Iterative graph DFS with an explicit LIFO stack; a node is finalised when
popped (its parent is the node that pushed it last), and visited nodes are skipped.

**Why it exists.** The other canonical uninformed strategy; low memory on narrow spaces and a
useful worst case.

**Complexity.** O(V + E) time, O(V) space (O(depth) for tree search).

**When it performs well.** Reachability checks; deep, narrow search spaces where any solution
will do.

**In FleetMind.** Completes, but the first path it finds wanders through the city (6× the
optimal travel time on average). Robots drive far more, need charging constantly and some run
out of battery — the experiments show the fleet collapsing. That is the expected and
instructive result.

## Greedy Best-First Search — `planning/greedy.py`

**What it does.** Priority queue ordered by the heuristic h(n) only (straight-line estimate to
the goal). Expands the node that *looks* closest.

**Why it exists.** The simplest informed search; shows the power and the danger of heuristics.

**Complexity.** O(E log V) worst case; usually far less.

**When it performs well.** When the straight line is a good guide and planning time matters
most.

**In FleetMind.** The fastest planner by a wide margin (~17 expansions per search versus ~90 for
A* and ~185 for Dijkstra), but it ignores cost already paid, so it happily takes slow local
streets or jammed roads that point at the goal (~15–17 % worse travel time).

## Dijkstra (uniform-cost search) — `planning/dijkstra.py`

**What it does.** Priority queue ordered by g(n), the cheapest known cost from the start, with
lazy deletion of stale entries.

**Why it exists.** Optimal shortest paths on graphs with non-negative weights, without needing
a heuristic.

**Complexity.** O((V + E) log V) with a binary heap.

**When it performs well.** Weighted graphs without a good heuristic; one-to-many queries.

**In FleetMind.** Optimal, traffic-aware routes. It expands every node cheaper than the goal in
all directions — ~185 expansions per search.

## A* — `planning/astar.py`

**What it does.** Priority queue ordered by f(n) = g(n) + h(n); ties broken toward larger g.
Nodes are re-opened if a cheaper path is found (never needed with a consistent heuristic, but it
keeps the implementation correct for merely admissible ones).

**Why it exists.** Optimal like Dijkstra, but focused toward the goal by the heuristic.

**Complexity.** O((V + E) log V) worst case; with a good heuristic it expands a fraction of the
graph.

**When it performs well.** Weighted spatial graphs with a meaningful distance heuristic — exactly
FleetMind's setting.

**In FleetMind.** Identical routes and fleet outcomes to Dijkstra (verified in every experiment)
with roughly half the expansions. It is the default planner.

---

## Heuristics — `planning/heuristics.py`

Costs are times, so heuristics convert distance to time with `graph.min_cost_per_meter`
= 1 / (8 m/s × 1.35), the cost of one metre on the fastest road class in free-flowing traffic.

| Heuristic | Formula | Properties on FleetMind's graph |
|---|---|---|
| `euclidean` (default) | ‖p(n) − p(goal)‖ × min_cost_per_meter | **Admissible and consistent**: every road is a straight segment no cheaper per metre than the bound, and traffic only increases cost |
| `manhattan` | (|dx| + |dy|) × min_cost_per_meter | Admissible only on axis-aligned grids; here diagonal roads make it overestimate, so A* may return suboptimal paths |
| `zero` | 0 | A* becomes Dijkstra; Greedy becomes an arbitrary-order search |

Tests verify admissibility and consistency of the Euclidean heuristic over the whole city
(including under heavy congestion), Manhattan's admissibility on a grid, and that Manhattan
overestimates somewhere on the generated city.

> A real bug this caught: road lengths were first rounded independently of the rounded node
> coordinates, which made some roads 0.0005 m *shorter* than the straight line between their
> endpoints — a heuristic violation of 0.0005 s. Lengths are now computed from the stored
> coordinates exactly.

---

## Task allocation — `allocation/`

Every 2 simulated seconds the allocator takes the most urgent pending orders (CRITICAL first,
then earliest deadline, max 24 per round) and scores every robot for each:

```
travel   = time until the robot is free (remaining route + queued stops + dwell/charge time)
           + estimated drive to the pickup                       [seconds]
workload = 90 s × orders already queued on the robot
battery  = 6 s × max(0, 40 − battery % after the job)
deadline = 3 s × max(0, estimated delivery time − deadline)
score    = travel + workload + battery + deadline                (lower wins)
```

**Hard constraints** (ineligible, with the reason recorded): offline; at capacity; recharging
below 80 %; heading to a charger; energy for queued work + this job + reaching a charger
afterwards + a 6 % floor exceeds the battery.

**Estimates** use straight-line distance × 1.4 (the measured mean detour of generated cities is
1.43) with a 25 % energy safety margin. The robot then plans the real route with the configured
algorithm and re-checks energy on the real route.

**Explanations.** Each assignment stores the components, reasons ("closest available robot —
pickup ETA 1m 35s", "sufficient battery — 51 % now, ≈18 % after delivery", "estimated arrival
within deadline (6m 32s slack)", …), the runner-up, the top candidates with their component
breakdown, and counts of rejection reasons.

**Preemption.** If a CRITICAL order would be late (or has no eligible robot), the allocator
considers robots still *driving to pick up* a LOW/NORMAL order. If one could deliver the
CRITICAL order at least 60 s sooner than the best free robot, the lower-priority order is
released back to the queue and the robot is reassigned. The preemption is logged with its
justification.

---

## Replanning triggers — `agents/robot.py`

| Trigger | Detected by | Response |
|---|---|---|
| Road on remaining route known closed | Own perception or fleet broadcast | Hold, U-turn if on the closed road, replan from the next junction (old route shown as invalidated) |
| Congestion on remaining route | Traffic feed broadcast | Re-plan; switch only if the alternative is ≥ 8 % cheaper, otherwise keep (both logged) |
| Remaining route + reserve exceeds battery | Junction battery check, battery-fault event | Insert a charge stop, choose a station by ETA + expected queue, verify reachability on the planned route |
| CRITICAL order inserted ahead | Allocator | Replan to the new pickup |
| Order cancelled / preempted | Allocator / event | Replan to the next stop or finish the current road and idle |
| Charging station unavailable | Event | Re-select another station |
