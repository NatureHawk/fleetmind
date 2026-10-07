from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_repository
from app.db.repository import Repository

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def runs(mode: str | None = None, limit: int = Query(30, ge=1, le=200), repo: Repository = Depends(get_repository)):
    return await asyncio.to_thread(repo.list_runs, limit, mode)


@router.get("/{run_id}")
async def run(run_id: str, repo: Repository = Depends(get_repository)):
    data = await asyncio.to_thread(repo.get_run, run_id)
    if data is None:
        raise HTTPException(404, f"run {run_id} not found")
    return data


@router.get("/{run_id}/events")
async def run_events(run_id: str, kind: str | None = None, limit: int = Query(500, ge=1, le=5000),
                     repo: Repository = Depends(get_repository)):
    return await asyncio.to_thread(repo.run_events, run_id, limit, kind)
