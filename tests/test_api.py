"""Task 5 tests: end-to-end over HTTP with the provided `client` fixture.

`conftest.py` resets the global store before and after each test, so HTTP tests always start
clean. These tests exercise the full stack — Pydantic validation, route lookup, per-run
Workspace and registry, the agent loop, and the verdict — through the same surface a real
caller would use.
"""

from __future__ import annotations


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_create_task_returns_a_task_with_an_id(client):
    spec = {
        "goal": "follow up with Acme",
        "scenario": "send_followup",
        "autonomy": "autonomous",
        "expected_effects": [
            {"tool": "send_message", "match": {"contact_id": "c_1"}}
        ],
    }

    response = client.post("/api/v1/tasks", json=spec)

    assert response.status_code == 200
    task = response.json()
    assert task["id"].startswith("t_")
    assert task["goal"] == "follow up with Acme"
    assert task["autonomy"] == "autonomous"
    assert task["scenario"] == "send_followup"


def test_get_task_returns_404_for_unknown_id(client):
    response = client.get("/api/v1/tasks/t_nope")
    assert response.status_code == 404


def test_create_task_then_start_run_completes_and_passes_verification(client):
    """The happy path through the full stack: create, run, verified."""
    spec = {
        "goal": "follow up with Acme",
        "scenario": "send_followup",
        "autonomy": "autonomous",
        "expected_effects": [
            {"tool": "send_message", "match": {"contact_id": "c_1"}}
        ],
    }
    task_id = client.post("/api/v1/tasks", json=spec).json()["id"]

    response = client.post("/api/v1/runs", json={"task_id": task_id})

    assert response.status_code == 201
    run = response.json()
    assert run["id"].startswith("r_")
    assert run["task_id"] == task_id
    assert run["status"] == "completed"
    assert run["autonomy"] == "autonomous"
    assert len(run["effects"]) == 1
    assert run["effects"][0]["tool"] == "send_message"
    assert run["effects"][0]["simulated"] is False
    assert run["verdict"]["passed"] is True
    # the run's trail is populated and readable
    assert len(run["steps"]) > 0


def test_start_run_404_when_task_does_not_exist(client):
    response = client.post("/api/v1/runs", json={"task_id": "t_nope"})
    assert response.status_code == 404


def test_start_run_shadow_simulates_without_changing_the_world(client):
    """The whole point of shadow: the verdict still passes, nothing really happened."""
    spec = {
        "goal": "follow up with Acme",
        "scenario": "send_followup",
        "autonomy": "shadow",
        "expected_effects": [
            {"tool": "send_message", "match": {"contact_id": "c_1"}}
        ],
    }
    task_id = client.post("/api/v1/tasks", json=spec).json()["id"]

    run = client.post("/api/v1/runs", json={"task_id": task_id}).json()

    assert run["status"] == "completed"
    assert len(run["effects"]) == 1
    assert run["effects"][0]["simulated"] is True
    assert run["verdict"]["passed"] is True


def test_get_run_returns_the_full_trace(client):
    spec = {"goal": "no-op", "scenario": "default", "autonomy": "autonomous"}
    task_id = client.post("/api/v1/tasks", json=spec).json()["id"]
    run_id = client.post("/api/v1/runs", json={"task_id": task_id}).json()["id"]

    response = client.get(f"/api/v1/runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["id"] == run_id
    assert response.json()["status"] == "completed"


def test_get_run_returns_404_for_unknown_id(client):
    response = client.get("/api/v1/runs/r_nope")
    assert response.status_code == 404