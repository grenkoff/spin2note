"""HTTP-layer tests for the analytics endpoints (auth wiring + response shapes).

The ClickHouse query functions are stubbed so these run without a database; real query
correctness is covered by the end-to-end check against a live ClickHouse.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from spin2note_api.clickhouse import queries
from spin2note_api.clickhouse.client import get_api_client
from spin2note_api.http.auth import require_user
from spin2note_api.main import create_app

USER = "00000000-0000-0000-0000-000000000009"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {"sub": USER}
    app.dependency_overrides[get_api_client] = lambda: object()

    async def fake_overview(_c: Any, _u: Any, _f: Any) -> dict[str, Any]:
        return {
            "total_hands": 10,
            "total_tournaments": 2,
            "avg_multiplier": 2.5,
            "by_stack": [{"effective_stack_bb": 15, "hands": 10, "result": 120.0, "winrate": 0.6}],
            "chips_timeline": [{"idx": 1, "at": "2026-01-07T22:54:43", "cumulative": 120.0}],
            "dollars_timeline": [{"idx": 1, "at": "2026-01-07T22:54:43", "cumulative": -0.25}],
        }

    async def fake_recent(_c: Any, _u: Any, _l: int) -> list[dict[str, Any]]:
        return [
            {
                "source_hand_id": "SG1",
                "played_at": "2026-01-07T22:54:43",
                "tournament_format": "3max",
                "effective_stack_bb": 15,
                "position": "SB",
                "result": -300.0,
                "board": "7h 5d 4d 4s 9s",
            }
        ]

    monkeypatch.setattr(queries, "overview", fake_overview)
    monkeypatch.setattr(queries, "recent_hands", fake_recent)
    return TestClient(app)


def test_overview_requires_shape(client: TestClient) -> None:
    r = client.get("/stats/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["total_hands"] == 10
    assert body["by_stack"][0]["winrate"] == 0.6


def test_overview_rejects_bad_format(client: TestClient) -> None:
    assert client.get("/stats/overview", params={"format": "9max"}).status_code == 422


def test_recent_hands(client: TestClient) -> None:
    r = client.get("/hands/recent", params={"limit": 10})
    assert r.status_code == 200
    assert r.json()[0]["source_hand_id"] == "SG1"


def test_recent_hands_limit_bounds(client: TestClient) -> None:
    assert client.get("/hands/recent", params={"limit": 0}).status_code == 422
    assert client.get("/hands/recent", params={"limit": 999}).status_code == 422
