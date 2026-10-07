# Architecture

## Overview

```
frontend/  React 18 + TypeScript + Vite — operations console
backend/   FastAPI + Pydantic + SQLAlchemy 2 + Alembic — simulation, API, persistence
           PostgreSQL 16 (SQLite fallback for zero-infrastructure development)
```

The browser never simulates anything. It renders server state, interpolating robot positions
between snapshots for smooth motion, and sends commands over REST.

## Backend layout

```
app/
  main.py                  application factory, lifespan (DB connect + migrate, services)
  api/
    deps.py                dependency providers
    routes/                simulation, environment, robots, orders, events, experiments,
                           metrics, algorithms, scenarios, runs, ws
  core/
    config.py              settings (FLEETMIND_* env vars)
    simulation_clock.py    fixed-step clock + wall-clock pacer
    event_bus.py           synchronous publish/subscribe (Observer)
    rng.py                 independent seeded random streams
    geometry.py, formatting.py
  simulation/
    environment.py         ground-truth road graph, movement/energy constants
    world_model.py         the fleet's shared belief (implements SearchGraph)
    generator.py           procedural city generation
    orders.py              orders, order book, arrival stream
    events.py              event types, scheduler, scenario incident generation
    event_processor.py     applies events to truth / belief / agents
    scenarios.py           ScenarioConfig + presets
    demo.py                guided-demo director
    timeline.py            explainable decision log
    engine.py              the deterministic tick loop
    snapshot.py            API / WebSocket serialisation
  agents/
    robot.py               RobotAgent: perceive → decide → act → replan
    agent_manager.py       fleet tick + world-change notifications
    communication.py       fleet channel (blackboard updates + broadcasts)
    charging.py            charging network (slots, reservations, queues)
    battery.py             energy model and thresholds
    fleet_factory.py       heterogeneous fleet creation
    context.py             what an agent may use during a tick
  planning/
    planner_interface.py   PathPlanner / SearchGraph protocols, SearchResult, SearchTrace
    bfs.py dfs.py greedy.py dijkstra.py astar.py
    heuristics.py          euclidean, manhattan, zero
    registry.py            factory + algorithm catalogue
    route_service.py       active strategy + cache + telemetry
  allocation/
    scoring.py             commitments and candidate evaluation
    task_allocator.py      dispatch policy, explanations, preemption
  metrics/
    collector.py           search, delivery, energy, utilisation metrics + time series
    experiment_runner.py   controlled multi-algorithm runs, aggregation, fairness report
  models/                  Pydantic request/response schemas
  db/
    tables.py              ORM tables
    session.py             connect, migrate, fallback
    repository.py          persistence operations
  services/
    simulation_service.py  live runtime: pacing, commands, WebSocket fan-out
    experiment_service.py  background experiments in a process pool
    persistence.py         batched persistence of a live run
alembic/                   migrations (0001 initial schema)
tests/                     unit/ and integration/
```

## Frontend layout

```
src/
  main.tsx                 router, fonts, stream start
  styles/global.css        design tokens and components
  lib/
    api.ts                 typed REST client
    types.ts               payload types (mirror backend/app/simulation/snapshot.py)
    formatters.ts, theme.ts
    simulation/
      store.ts             zustand store (map, snapshot, events, selection, tools, layers)
      stream.ts            WebSocket with reconnect and robot focus
      motion.ts            per-robot interpolation outside React
  hooks/                   useCommands (REST commands + toasts), usePoll
  components/
    layout/                AppShell (top bar, toasts)
    simulation/            renderer.ts (Canvas), MapCanvas, MapControls, LayersPanel,
                           DemoStepper, HoverCard, KpiStrip
    fleet/ orders/ events/ inspector/ analytics/ common/
  pages/                   Operations, Analytics, Experiments, Algorithms, Scenarios
```

## Data flow

1. **Startup** — the lifespan connects to PostgreSQL (3 s timeout), runs `alembic upgrade head`,
   falls back to SQLite if needed, creates `SimulationRuntime` (loads the default scenario,
   paused) and `ExperimentService`.
2. **Live loop** — an asyncio task wakes ~120×/s. When running, the `FixedStepPacer` converts
   elapsed wall time × speed into whole ticks (16 ticks/s at 1×, 0.5 s each) and the engine
   steps. Every ~66 ms a snapshot is built per client (each client has its own timeline cursor
   and optional robot focus) and queued; slow clients drop old frames rather than block.
3. **Commands** — REST handlers are `async` and run on the same event loop as the simulation,
   so the engine is never accessed concurrently. Operator events are validated and applied
   immediately.
4. **Experiments** — payloads are dispatched to a `ProcessPoolExecutor` (spawn context). Each
   worker builds its own engine and runs it headless; results stream back as they finish.
5. **Persistence** — live runs buffer timeline entries (Observer on `timeline.entry`) and metric
   samples, flushing every 2 s via `asyncio.to_thread`. Final robot/order records and the summary
   are written when the run is reset or the server stops. Experiments persist each run and the
   aggregates when complete.

## Key design decisions

| Decision | Why |
|---|---|
| Simulation in the backend, rendering in the browser | One source of truth; the same engine powers experiments; the UI can't drift from the model |
| Fixed timestep, no wall clock in the engine | Determinism and fair experiments; rendering FPS never changes outcomes |
| Ground truth vs. shared belief | Makes perception, communication and replanning meaningful instead of cosmetic |
| Plan one leg at a time | Later legs are planned on the newest knowledge; avoids stale multi-leg plans |
| Allocation uses straight-line estimates | Cheap (O(robots × orders) per round) and independent of the planner being evaluated |
| Route cache keyed by world-model version | Identical queries are reused; any traffic/closure update invalidates everything automatically |
| Synchronous event bus | Deterministic ordering inside a tick; no hidden concurrency |
| Canvas 2D renderer with Path2D batching | Hundreds of roads/blocks and dozens of robots at 60 fps without a heavy dependency |
| WebSocket for state, REST for commands | No polling for positions; commands get proper status codes and validation |
| Process pool for experiments | True parallelism and the live simulation keeps its CPU |
| SQLite fallback | The app always starts; health and the top bar make the fallback explicit |

## Persistence schema

| Table | Contents |
|---|---|
| `environments` | one row per generated city (seed, fingerprint, size) |
| `nodes`, `roads` | the city graph for each environment (roads include travel time and energy cost) |
| `simulation_runs` | live and experiment runs: config, fingerprints, status, summary metrics |
| `simulation_events` | the decision timeline of live runs |
| `metrics` | periodic metric samples (time series) |
| `robots`, `orders` | final per-robot and per-order records of a run |
| `experiments` | experiment definition, status, aggregates, fairness report |
| `algorithm_results` | one row per (algorithm, repetition) with key metrics as columns + full JSON |
