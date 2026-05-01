import pytest

from llmgames import Audience, GameConfig, GameSession, JSONFileSessionStore, Player, restore_session, snapshot_session
from llmgames.games import SplitOrStealKernel, TicTacToeKernel
from llmgames.replay import comparable_trace


@pytest.mark.asyncio
async def test_json_store_recovers_projection_after_refresh(tmp_path) -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    store = JSONFileSessionStore(tmp_path)

    await store.save(snapshot_session(session))
    loaded = await store.load(session.session_id)
    assert loaded is not None
    restored = restore_session(TicTacToeKernel(), loaded)
    projection = await restored.projection(Audience.player("alice"))

    assert projection.session_id == session.session_id
    assert projection.visible_state["board"] == [[None, None, None], [None, None, None], [None, None, None]]
    assert [request.spec_key for request in projection.visible_requests] == ["place_mark:alice"]


@pytest.mark.asyncio
async def test_restored_session_can_continue_play(tmp_path) -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    await session.submit("req_1", {"row": 0, "col": 0}, actor_id="alice", idempotency_key="a1")
    store = JSONFileSessionStore(tmp_path)

    await store.save(snapshot_session(session))
    loaded = await store.load(session.session_id)
    assert loaded is not None
    restored = restore_session(TicTacToeKernel(), loaded)
    result = await restored.submit("req_2", {"row": 1, "col": 1}, actor_id="bob", idempotency_key="b1")
    projection = await restored.projection(Audience.public())

    assert result.accepted is True
    assert projection.visible_state["board"][0][0] == "X"
    assert projection.visible_state["board"][1][1] == "O"
    assert projection.visible_state["current_player_id"] == "alice"


@pytest.mark.asyncio
async def test_snapshot_reload_preserves_comparable_trace(tmp_path) -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    await session.submit("req_1", {"row": 0, "col": 0}, actor_id="alice", idempotency_key="a1")
    before = await comparable_trace(session)
    store = JSONFileSessionStore(tmp_path)

    await store.save(snapshot_session(session))
    loaded = await store.load(session.session_id)
    assert loaded is not None
    restored = restore_session(TicTacToeKernel(), loaded)
    after = await comparable_trace(restored)

    assert after == before


@pytest.mark.asyncio
async def test_store_lists_and_deletes_session_ids(tmp_path) -> None:
    session = GameSession(TicTacToeKernel(), _config(), session_id="game_one")
    await session.start()
    store = JSONFileSessionStore(tmp_path)

    await store.save(snapshot_session(session))
    assert await store.list_session_ids() == ["game_one"]

    await store.delete("game_one")
    assert await store.load("game_one") is None
    assert await store.list_session_ids() == []


def test_snapshot_rejects_unstarted_session() -> None:
    session = GameSession(TicTacToeKernel(), _config())

    with pytest.raises(RuntimeError, match="before it has started"):
        snapshot_session(session)


@pytest.mark.asyncio
async def test_restore_rejects_wrong_kernel(tmp_path) -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    store = JSONFileSessionStore(tmp_path)

    await store.save(snapshot_session(session))
    loaded = await store.load(session.session_id)
    assert loaded is not None

    with pytest.raises(ValueError, match="cannot be restored"):
        restore_session(SplitOrStealKernel(), loaded)


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])