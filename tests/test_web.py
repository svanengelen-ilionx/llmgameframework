import json

import httpx
import pytest

from llmgames import GameConfig, GameSession, JSONFileSessionStore, Player, create_game_app, snapshot_session
from llmgames.games import TicTacToeKernel


@pytest.mark.asyncio
async def test_projection_endpoint_recovers_stored_session(tmp_path) -> None:
    client = _client(tmp_path)

    await client.post("/sessions", json={"session_id": "web_1", "config": _config_json()})
    response = await client.get("/sessions/web_1/projection", params={"audience_kind": "player", "player_id": "alice"})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "web_1"
    assert [request["spec_key"] for request in body["visible_requests"]] == ["place_mark:alice"]
    await client.aclose()


@pytest.mark.asyncio
async def test_submission_endpoint_persists_updated_projection(tmp_path) -> None:
    client = _client(tmp_path)

    await client.post("/sessions", json={"session_id": "web_1", "config": _config_json()})
    result = await client.post(
        "/sessions/web_1/requests/req_1/submissions",
        json={"payload": {"row": 0, "col": 0}, "actor_id": "alice", "idempotency_key": "a1"},
    )
    projection = await client.get("/sessions/web_1/projection", params={"audience_kind": "player", "player_id": "bob"})

    assert result.status_code == 200
    assert result.json()["accepted"] is True
    assert projection.json()["visible_state"]["board"][0][0] == "X"
    assert [request["spec_key"] for request in projection.json()["visible_requests"]] == ["place_mark:bob"]
    await client.aclose()


@pytest.mark.asyncio
async def test_sse_event_stream_resumes_from_cursor(tmp_path) -> None:
    client = _client(tmp_path)

    await client.post("/sessions", json={"session_id": "web_1", "config": _config_json()})
    await client.post(
        "/sessions/web_1/requests/req_1/submissions",
        json={"payload": {"row": 0, "col": 0}, "actor_id": "alice", "idempotency_key": "a1"},
    )
    first_stream = await client.get("/sessions/web_1/events")
    resumed_stream = await client.get("/sessions/web_1/events", params={"cursor": 1})

    assert "id: 1" in first_stream.text
    assert "event: mark_placed" in first_stream.text
    assert _event_data(first_stream.text)["payload"] == {"player_id": "alice", "row": 0, "col": 0, "mark": "X"}
    assert resumed_stream.text == ""
    await client.aclose()


@pytest.mark.asyncio
async def test_debug_events_are_filtered_from_public_sse(tmp_path) -> None:
    store = JSONFileSessionStore(tmp_path)
    session = GameSession(TicTacToeKernel(), _config(), session_id="web_1")
    await session.start()
    session.record_event("public_event", visibility="public")
    session.record_event("debug_event", visibility="debug")
    await store.save(snapshot_session(session))
    client = _client(tmp_path, store=store)

    public_stream = await client.get("/sessions/web_1/events")
    debug_stream = await client.get("/sessions/web_1/events", params={"audience_kind": "debug"})

    assert "event: public_event" in public_stream.text
    assert "event: debug_event" not in public_stream.text
    assert "event: public_event" in debug_stream.text
    assert "event: debug_event" in debug_stream.text
    await client.aclose()


def _client(tmp_path, *, store: JSONFileSessionStore | None = None) -> httpx.AsyncClient:
    app = create_game_app(TicTacToeKernel(), store or JSONFileSessionStore(tmp_path))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])


def _config_json() -> dict:
    return _config().model_dump(mode="json")


def _event_data(stream_text: str) -> dict:
    for line in stream_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError("No SSE data line found")