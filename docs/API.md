# API

Base URL `http://localhost:8000/api` (through the dev server or nginx: `/api`). Interactive
OpenAPI docs: `http://localhost:8000/docs`. Errors use standard status codes with
`{"detail": "..."}`: 404 unknown entity, 409 invalid state (e.g. stepping while running), 422
validation failure, 503 persistence disabled.

## Simulation

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/simulation/status` | – | running, speed, clock, scenario, algorithm, fingerprints |
| GET | `/simulation/state` | – | status + full snapshot |
| POST | `/simulation/start` · `/resume` | – | |
| POST | `/simulation/pause` | – | |
| POST | `/simulation/step` | `{"ticks": 4}` | paused only (409 otherwise) |
| POST | `/simulation/reset` | `{"scenario": "surge", "seed": 9}` or `{"config": ScenarioConfig}` | omitted fields keep current values |
| POST | `/simulation/speed` | `{"speed": 4}` | one of 0.5, 1, 2, 4, 8 |
| POST | `/simulation/algorithm` | `{"algorithm": "astar", "heuristic": "euclidean"}` | applies to new plans |

## World

| Method | Path | Notes |
|---|---|---|
| GET | `/environment` | static map: nodes, roads, blocks (faces), districts, chargers |
| GET | `/environment/roads/{id}` | distance, class, true & known traffic, travel time, planner cost, energy cost, closed / known, robots routed |
| GET | `/environment/nodes/{id}` | node detail; chargers include occupancy, queue, available capacity, inbound reservations |
| GET | `/environment/chargers` | all stations |
| GET | `/robots` | per-robot metrics |
| GET | `/robots/{id}` | inspector detail: plan, stops, loop state, decision log, timeline |
| GET | `/orders?status=PENDING&limit=200` | |
| GET | `/orders/{id}` | includes the assignment explanation and history |

## Events

| Method | Path | Notes |
|---|---|---|
| POST | `/events` | inject an operator event (applied immediately) |
| GET | `/events?since=&robot_id=&order_id=&category=&kind=&limit=` | decision timeline |
| GET | `/events/types` | event catalogue |
| GET | `/events/scheduled` | upcoming scenario incidents (experimenter's view) |

`POST /events` body:

```json
{"type": "ROAD_BLOCKED", "road_id": 112, "duration_s": 600}
{"type": "TRAFFIC_INCREASE", "road_ids": [5, 6, 7], "level": "JAMMED", "duration_s": 300}
{"type": "NEW_ORDER", "priority": "CRITICAL", "source": 12, "destination": 40}
{"type": "ROBOT_LOW_BATTERY", "robot_id": "R-05", "level": 0.12}
{"type": "ROBOT_FAILURE", "robot_id": "R-03", "duration_s": 240}
{"type": "CHARGING_STATION_BUSY", "node_id": 77, "duration_s": 300}
{"type": "ORDER_CANCELLED", "order_id": "ORD-014"}
```

Targets may be omitted: e.g. `ROAD_BLOCKED` without `road_id` closes a road a few segments ahead
on the busiest active route; `ROBOT_LOW_BATTERY` picks a busy robot.

## Experiments, metrics, algorithms, scenarios, runs

| Method | Path | Notes |
|---|---|---|
| POST | `/experiments/run` | `{"scenario": "baseline", "seed": 42173, "algorithms": [...], "repetitions": 3, "duration_s": 1800}` or `{"config": ScenarioConfig, ...}` → 202 with the job |
| GET | `/experiments` | list (persisted + in-progress) |
| GET | `/experiments/{id}` | progress, aggregates, fairness report, per-run results with time series |
| DELETE | `/experiments/{id}` | |
| GET | `/metrics` | current run: global, per-algorithm, per-robot, time series, recent searches |
| GET | `/algorithms` | catalogue + live stats + heuristics |
| POST | `/algorithms/trace` | `{"algorithm"?, "start"?, "goal"?, "heuristic"?}` → traced searches on the current world model |
| GET | `/scenarios` · `/scenarios/{key}` · `/scenarios/schema` | presets and the builder's JSON schema |
| GET | `/runs?mode=live` · `/runs/{id}` · `/runs/{id}/events` | persisted run history |
| GET | `/health` | status and database connection (dialect, fallback) |

## WebSocket `/ws/simulation`

Server → client:

* `{"type": "static", "version": n, "map": {...}, "status": {...}}` — on connect and after each reset.
* `{"type": "snapshot", ...}` at ~15 Hz:

  | Field | Content |
  |---|---|
  | `t`, `tick`, `running`, `speed` | clock |
  | `robots[]` | id, status, x, y, heading, battery, orders, carrying, target stop, remaining route (node ids), invalidated route, replans, algorithm, route cost |
  | `orders[]`, `recent_orders[]` | open orders; recently closed |
  | `roads[]` | only roads with non-default state: traffic, blocked, known to fleet |
  | `chargers[]` | slots, charging, queue, reserved, availability |
  | `kpis` | global metrics |
  | `events[]`, `last_seq` | new timeline entries since this client's cursor |
  | `demo` | phase list and progress (guided demo) |
  | `focus` | full robot detail for the robot this client focuses on |

Client → server:

* `{"type": "focus", "robot_id": "R-07"}` (or `null`) — include inspector detail in snapshots.
* `{"type": "resync"}` — resend the static map.
