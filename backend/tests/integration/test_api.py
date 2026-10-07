"""HTTP + WebSocket API against a real app instance (SQLite database in a temp dir)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", database_fallback_url="",
                        experiment_workers=0, default_scenario="baseline")
    with TestClient(create_app(settings)) as c:
        yield c


def test_health_reports_database(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] and body["database"]["dialect"] == "sqlite"


def test_simulation_controls(client):
    st = client.get("/api/simulation/status").json()
    assert st["running"] is False and st["t"] == 0
    assert client.post("/api/simulation/step", json={"ticks": 40}).json()["t"] == pytest.approx(20.0)
    assert client.post("/api/simulation/start").json()["running"] is True
    assert client.post("/api/simulation/step", json={"ticks": 1}).status_code == 409
    assert client.post("/api/simulation/pause").json()["running"] is False
    assert client.post("/api/simulation/speed", json={"speed": 3}).status_code == 422
    assert client.post("/api/simulation/speed", json={"speed": 4}).json()["speed"] == 4
    assert client.post("/api/simulation/algorithm", json={"algorithm": "dijkstra"}).json()["algorithm"] == "dijkstra"
    assert client.post("/api/simulation/algorithm", json={"algorithm": "magic"}).status_code == 422
    r = client.post("/api/simulation/reset", json={"scenario": "surge", "seed": 9})
    assert r.json()["scenario"]["key"] == "surge" and r.json()["t"] == 0
    assert client.post("/api/simulation/reset", json={"scenario": "nope"}).status_code == 404
    bad = {"config": {"robots": 0}}
    assert client.post("/api/simulation/reset", json=bad).status_code == 422


def test_events_and_inspection(client):
    client.post("/api/simulation/step", json={"ticks": 120})
    r = client.post("/api/events", json={"type": "ROAD_BLOCKED", "road_id": 3})
    assert r.status_code == 201
    assert any(e["kind"] == "ROAD_BLOCKED" for e in r.json()["timeline"])
    assert client.get("/api/environment/roads/3").json()["blocked"] is True
    assert client.post("/api/events", json={"type": "ROAD_BLOCKED", "road_id": 99999}).status_code == 404
    assert client.post("/api/events", json={"type": "ROBOT_FAILURE", "robot_id": "R-99"}).status_code == 404
    assert client.post("/api/events", json={"type": "NEW_ORDER", "priority": "URGENT"}).status_code == 422
    assert client.post("/api/events", json={"type": "NEW_ORDER", "priority": "CRITICAL"}).status_code == 201
    robot = client.get("/api/robots/R-01").json()
    assert {"loop", "decisions", "stats", "battery_pct", "timeline"} <= set(robot)
    assert client.get("/api/robots/R-77").status_code == 404
    orders = client.get("/api/orders").json()
    assert orders and client.get(f"/api/orders/{orders[0]['id']}").status_code == 200
    charger = next(n for n in client.get("/api/environment").json()["nodes"] if n["kind"] == "charger")
    station = client.get(f"/api/environment/nodes/{charger['id']}").json()["station"]
    assert {"occupancy", "queue", "available_capacity"} <= set(station)


def test_algorithm_catalog_and_trace(client):
    cat = client.get("/api/algorithms").json()
    assert [a["key"] for a in cat["algorithms"]] == ["bfs", "dfs", "greedy", "dijkstra", "astar"]
    trace = client.post("/api/algorithms/trace", json={"start": 0, "goal": 100}).json()
    by = {r["algorithm"]: r for r in trace["results"]}
    assert by["astar"]["cost"] == pytest.approx(by["dijkstra"]["cost"])
    assert len(by["bfs"]["trace"]) == by["bfs"]["nodes_explored"]
    assert client.post("/api/algorithms/trace", json={"algorithm": "x"}).status_code == 422


def test_metrics_and_scenarios(client):
    client.post("/api/simulation/step", json={"ticks": 200})
    m = client.get("/api/metrics").json()
    assert m["global"]["orders_created"] > 0 and m["robots"] and m["timeseries"]
    scenarios = client.get("/api/scenarios").json()
    assert [s["key"] for s in scenarios] == ["demo", "baseline", "congestion", "road_closure", "battery_critical", "surge"]


def test_experiment_runs_and_persists(client):
    r = client.post("/api/experiments/run", json={"scenario": "baseline", "algorithms": ["astar", "bfs"],
                                                  "duration_s": 300})
    assert r.status_code == 202
    exp_id = r.json()["id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        body = client.get(f"/api/experiments/{exp_id}").json()
        if body["status"] != "running":
            break
        time.sleep(0.3)
    assert body["status"] == "completed"
    assert body["fairness"]["identical_conditions"] is True
    assert set(body["aggregates"]) == {"astar", "bfs"}
    time.sleep(0.5)
    listed = client.get("/api/experiments").json()
    assert any(x["id"] == exp_id for x in listed)
    runs = client.get("/api/runs", params={"mode": "experiment"}).json()
    assert len(runs) >= 2
    assert client.post("/api/experiments/run", json={"algorithms": ["teleport"]}).status_code == 422


def test_websocket_stream(client):
    with client.websocket_connect("/ws/simulation") as ws:
        first = ws.receive_json()
        assert first["type"] == "static" and first["map"]["nodes"] and first["map"]["roads"]
        ws.send_json({"type": "focus", "robot_id": "R-02"})
        client.post("/api/simulation/step", json={"ticks": 10})
        for _ in range(10):
            msg = ws.receive_json()
            if msg["type"] == "snapshot" and msg.get("focus"):
                break
        assert msg["type"] == "snapshot"
        assert msg["focus"]["id"] == "R-02"
        assert len(msg["robots"]) == 15
