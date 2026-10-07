# Contributing

## Setup

See the README's *Local development*. Run the backend with `--reload` and the frontend with
`npm run dev`; the Vite dev server proxies `/api` and `/ws` to port 8000.

## Checks before a change lands

```bash
cd backend && pytest
cd frontend && npm run typecheck && npm run build
```

Keep the engine deterministic: no wall-clock reads, no unseeded randomness, no iteration over
unordered collections where order affects outcomes. `tests/unit/test_determinism.py` must pass.

## Adding a search algorithm

1. Create `backend/app/planning/<name>.py` with a class exposing `key`, `name` and
   `find_path(graph, start, goal, *, trace=False) -> SearchResult`. Use only the `SearchGraph`
   protocol (`neighbors`, `position`, `edge_cost`, `min_cost_per_meter`); record expansions with
   `SearchTrace.record` when tracing; count `nodes_explored` at expansion time.
2. Register it in `planning/registry.py` (`ALGORITHM_KEYS`, `create_planner`, `ALGORITHM_CATALOG`).
3. Add it to `ALGORITHM_ORDER`, `ALGORITHM_SHORT` and `ALGORITHM_COLOR` in
   `frontend/src/lib/theme.ts` (re-validate the categorical palette if you add a sixth colour).
4. Add tests (validity, optimality claims, failure case) and extend the independence test.

## Adding a scenario

Add an entry to `_PRESETS` and `SCENARIO_ORDER` in `backend/app/simulation/scenarios.py`. Any
`ScenarioConfig` field can be set; incidents are generated from the counts/probabilities.

## Adding an event type

Add it to `EventType` and `EVENT_DESCRIPTIONS` (`simulation/events.py`), implement
`_on_<type>` in `simulation/event_processor.py`, validate operator parameters in
`SimulationEngine.inject_event`, and expose it in the map's *Inject event* menu if useful.

## Database changes

Edit `app/db/tables.py`, then generate a migration:

```bash
cd backend
FLEETMIND_DATABASE_URL=postgresql+psycopg://fleetmind:fleetmind@localhost:5432/fleetmind \
  alembic revision --autogenerate -m "describe change"
```

Review the generated file; migrations run automatically on startup.

## Style

Python: type hints, small modules, docstrings that explain *why*. TypeScript: strict mode,
components per concern, colours and spacing from the CSS tokens in `styles/global.css`, text in
text tokens (never the data colour).
