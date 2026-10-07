"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    algorithms,
    environment,
    events,
    experiments,
    metrics,
    orders,
    robots,
    runs,
    scenarios,
    simulation,
    ws,
)
from app.core.config import Settings, get_settings
from app.db.repository import Repository
from app.db.session import connect_database
from app.services.experiment_service import ExperimentService
from app.services.simulation_service import SimulationRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = await asyncio.to_thread(connect_database, settings.database_url, settings.database_fallback_url or None)
        app.state.db = db
        app.state.repo = Repository(db) if db is not None else None
        app.state.runtime = SimulationRuntime(settings, app.state.repo)
        app.state.experiments = ExperimentService(settings, app.state.repo)
        await app.state.runtime.startup()
        yield
        await app.state.runtime.shutdown()
        app.state.experiments.shutdown()

    app = FastAPI(title="FleetMind API", version=__version__, lifespan=lifespan,
                  description="Autonomous multi-agent delivery planning and simulation platform.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    for module in (simulation, environment, robots, orders, events, experiments, metrics, algorithms, scenarios,
                   runs):
        app.include_router(module.router, prefix="/api")
    app.include_router(ws.router)

    @app.get("/api/health", tags=["system"])
    async def health():
        db = app.state.db
        return {"status": "ok", "version": __version__,
                "database": db.describe() if db is not None else {"connected": False}}

    return app


app = create_app()
