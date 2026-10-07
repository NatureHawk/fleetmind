# Simulation

## Time

* One tick = **0.5 simulated seconds** (`FLEETMIND_TICK_SECONDS`).
* At 1× the runtime executes 16 ticks per wall-clock second = **8 simulated seconds per second**.
  Speeds 0.5×, 1×, 2×, 4×, 8× scale the tick rate; the tick size never changes.
* The engine never reads the wall clock.

Per tick (`engine.step`):

1. Apply due events (scenario incidents, scheduled reopenings/clears).
2. Release newly arrived orders.
3. Demo director (guided demo only).
4. Task allocation (every 2 s).
5. `ChargingNetwork.promote` (queued robots take free slots), then each robot ticks in id order:
   **perceive → decide → act**.
6. Expire orders still unassigned 5 minutes after their deadline.
7. Sample metrics every 15 s.

## The city

Generated from the seed (`simulation/generator.py`): ~340 intersections from variable-radius
Poisson-disk sampling (industrial zones sparse, the commercial core dense), roads from the
Gabriel graph (planar — no crossings), acute-angle and random pruning (never disconnecting,
never creating dead ends), four near-straight arterial corridors and seven collector corridors.
Five warehouses sit in industrial zones, five chargers (2–3 slots) spread across the centre,
46 customers in residential/commercial zones. City blocks are the bounded faces of the planar
graph (count = E − V + 1, tested).

## Truth and belief

`Environment` holds the true traffic level and closure of each road. `WorldModel` holds what the
fleet believes and is the only graph planners search.

* **Traffic** is published by a city traffic feed: belief updates immediately.
* **Operator closures** are announced: belief updates immediately.
* **Incident closures** (scenarios, demo) change only the truth. A robot perceives a closure
  when it is at a junction adjacent to the road, or within 90 m of the junction it is driving
  to. It reports it on the fleet channel; the first report updates the world model and
  triggers a broadcast. A robot that arrives at a junction whose next road is closed stops,
  reports and replans — it can never drive onto a closed road.

## Movement and energy

```
speed  = robot_speed × class_factor / traffic_time_factor      (true traffic)
energy = distance × robot_energy_rate × traffic_energy_factor  (low 1.0 … jammed 1.55)
```

| Model | Speed | Capacity | Battery | Energy rate |
|---|---|---|---|---|
| Courier S | 1.18× | 1 | 520 Wh | 0.032 Wh/m |
| Courier M | 1.00× | 2 | 680 Wh | 0.038 Wh/m |
| Hauler L | 0.84× | 3 | 900 Wh | 0.047 Wh/m |

Each robot gets ±4 % speed and ±5 % efficiency jitter. Battery thresholds: 6 % planning floor,
20 % warning, idle robots below 35 % charge proactively, charging targets 95 % (or leaves at
80 % if work is queued). Charging power 3.6 Wh/s. A depleted robot stops where it is, fails any
parcel on board, returns unpicked orders to the queue and gets a field battery swap (30 %) after
8 minutes.

## Robot states

```
IDLE ──assign──▶ ASSIGNED ──▶ PLANNING ──plan──▶ EN_ROUTE ──arrive──▶ LOADING / DELIVERING
  ▲                                ▲                 │                         │
  │                                │       closure / congestion /              ▼
  │                                └──── REPLANNING ◀ battery / priority    next stop
  │                                                                            │
  └────────────────────────── no stops left ◀──────────────────────────────────┘
EN_ROUTE ─(charge stop)─▶ CHARGING or WAITING (queue) ─▶ next stop
any ─(failure / depletion)─▶ OFFLINE ─(recovery)─▶ IDLE
WAITING is also used when no route exists (retry every 20 s).
```

Dwell times: 1 s planning, 2 s replanning (the robot holds position), 10 s loading, 12 s hand-over.

## Events

| Type | Effect |
|---|---|
| `ROAD_BLOCKED` | Close a road (operator: announced; scenario/demo: hidden). Optional reopening. |
| `ROAD_REOPENED` | Reopen; belief updated |
| `TRAFFIC_INCREASE` | Raise a corridor to HIGH/JAMMED; traffic feed broadcast; affected robots re-evaluate. Optional clear. |
| `TRAFFIC_CLEAR` | Back to free flow |
| `NEW_ORDER` | Create an order (any priority) |
| `ORDER_CANCELLED` | Cancel an order not yet picked up; robot released |
| `ROBOT_LOW_BATTERY` | Drop a robot's charge; it re-checks feasibility immediately |
| `ROBOT_FAILURE` | Robot offline for a duration |
| `CHARGING_STATION_BUSY` | Station unavailable; reserved/queued robots choose another |

Scenario incidents are generated at start from the seed (`events.build_incidents`): congestion
corridors, closures weighted toward major roads (never bridges, so the city stays connected),
extra random closures with a per-minute probability, and robot failures.

## Scenarios

| Key | Robots | Orders | Environment | Purpose |
|---|---|---|---|---|
| `demo` | 12 | 9 + 1.3/min | scripted | presentation |
| `baseline` | 15 | 12 + 1.7/min | 4 % traffic | basic algorithm comparison |
| `congestion` | 15 | 12 + 1.7/min | 25 % traffic + 10 jams | weighted planning |
| `road_closure` | 15 | 12 + 1.7/min | 9 closures + 8 %/min random | replanning |
| `battery_critical` | 14 | 12 + 1.6/min | 6 robots at 14–26 % | battery-aware planning |
| `surge` | 25 | 40 + 7.5/min | jams, closures, 2 failures | allocation at scale |

The builder exposes every `ScenarioConfig` field (validated server-side).

## Guided demo

`simulation/demo.py` advances through seven phases at fixed simulated times (80 s traffic,
170 s closure, replanning when the closure is detected, 300 s battery fault, 400 s CRITICAL
order, 560 s final metrics and pause). It targets robots whose *current* routes make each effect
visible, e.g. the closure is placed 2–4 roads ahead of a driving robot and is a hidden incident,
so that robot must discover it. The demo is deterministic for a given seed.

## Performance

A 30-minute run of the 25-robot surge scenario (≈270 orders) completes headless in about 3 s on
a laptop CPU; baseline runs take ~0.6 s. Searches on the ~340-node graph take 0.1–0.7 ms. The
route cache, leg-by-leg planning, bounded allocation rounds and O(closures) perception checks
keep per-tick cost low.
