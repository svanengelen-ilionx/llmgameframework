import pytest
from typing import Any, cast

from llmgames import Audience, GameConfig, GameSession, Player, order_set_option
from llmgames.games import ComplexOrdersKernel, ComplexOrdersState
from llmgames.rules import RulesKernel
from llmgames.testing import replay_session, run_scripted_session


def test_order_set_option_marks_general_primitive() -> None:
    option = order_set_option(
        "hold",
        payload={"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
        order_count=1,
        subject_ids=["alice:unit_1"],
    )

    assert option.metadata == {
        "primitive": "order_set",
        "order_count": 1,
        "subject_ids": ["alice:unit_1"],
    }


@pytest.mark.asyncio
async def test_complex_orders_start_with_simultaneous_order_set_requests() -> None:
    session = GameSession(_kernel(), _config())

    await session.start()

    assert [(request.spec_key, request.kind, request.mode) for request in session.requests] == [
        ("order_set:alice:turn_1", "order_set", "barrier"),
        ("order_set:bob:turn_1", "order_set", "barrier"),
        ("order_set:carol:turn_1", "order_set", "barrier"),
    ]
    alice_request = (await session.projection(Audience.player("alice"))).visible_requests[0]
    assert alice_request.legal_options is not None
    assert alice_request.legal_options.kind == "order_set"
    assert alice_request.legal_options.options[0].metadata["primitive"] == "order_set"


@pytest.mark.asyncio
async def test_complex_orders_resolve_only_after_full_batch() -> None:
    session = GameSession(_kernel(), _config())
    await session.start()

    first = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "move", "target": "center"}]},
        actor_id="alice",
        idempotency_key="alice-orders",
    )
    partial_projection = await session.projection(Audience.public())

    assert first.accepted is True
    assert partial_projection.phase == "ordering"
    assert partial_projection.visible_state["submitted_player_ids"] == ["alice"]
    assert [request.status for request in session.requests] == ["pending", "pending", "pending"]

    await session.submit(
        "req_2",
        {"orders": [{"unit_id": "bob:unit_1", "action": "hold"}]},
        actor_id="bob",
        idempotency_key="bob-orders",
    )
    final = await session.submit(
        "req_3",
        {"orders": [{"unit_id": "carol:unit_1", "action": "move", "target": "center"}]},
        actor_id="carol",
        idempotency_key="carol-orders",
    )
    projection = await session.projection(Audience.public())

    assert final.accepted is True
    assert projection.phase == "complete"
    assert [request.status for request in session.requests] == ["resolved", "resolved", "resolved"]
    assert session.events[-1].kind == "order_batch_resolved"
    assert session.events[-1].payload["order_count"] == 3
    assert projection.visible_state["resolution_log"][0]["status"] == "blocked"
    assert projection.visible_state["resolution_log"][2]["status"] == "blocked"


@pytest.mark.asyncio
async def test_complex_orders_drafts_can_be_revised_before_final_batch() -> None:
    session = GameSession(_kernel(), _config())
    await session.start()

    draft = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "move", "target": "center"}]},
        actor_id="alice",
        idempotency_key="alice-draft-1",
        intent="draft",
    )
    revised = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
        actor_id="alice",
        idempotency_key="alice-draft-2",
        intent="draft",
    )
    projection = await session.projection(Audience.public())

    assert draft.accepted is True
    assert revised.accepted is True
    assert [submission.intent for submission in session.submissions] == ["draft", "draft"]
    assert session.requests[0].status == "pending"
    assert projection.visible_state["submitted_player_ids"] == []

    final = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "move", "target": "south"}]},
        actor_id="alice",
        idempotency_key="alice-final",
    )

    assert final.accepted is True
    assert session.requests[0].status == "pending"
    state = cast(ComplexOrdersState, session.state)
    assert state.submitted_player_ids == ["alice"]


@pytest.mark.asyncio
async def test_complex_orders_final_batch_ignores_previous_drafts() -> None:
    session = GameSession(_kernel(), _config())
    await session.start()

    await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "move", "target": "center"}]},
        actor_id="alice",
        idempotency_key="alice-draft",
        intent="draft",
    )
    await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
        actor_id="alice",
        idempotency_key="alice-final",
    )
    await session.submit(
        "req_2",
        {"orders": [{"unit_id": "bob:unit_1", "action": "hold"}]},
        actor_id="bob",
        idempotency_key="bob-final",
    )
    await session.submit(
        "req_3",
        {"orders": [{"unit_id": "carol:unit_1", "action": "move", "target": "center"}]},
        actor_id="carol",
        idempotency_key="carol-final",
    )
    projection = await session.projection(Audience.public())

    assert projection.phase == "complete"
    alice_outcome = projection.visible_state["resolution_log"][0]
    assert alice_outcome["action"] == "hold"
    assert alice_outcome["to"] == "north"


@pytest.mark.asyncio
async def test_complex_orders_idempotency_includes_submission_intent() -> None:
    session = GameSession(_kernel(), _config())
    await session.start()

    first = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
        actor_id="alice",
        idempotency_key="alice-orders",
        intent="draft",
    )
    retry = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
        actor_id="alice",
        idempotency_key="alice-orders",
        intent="draft",
    )
    conflict = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
        actor_id="alice",
        idempotency_key="alice-orders",
        intent="final",
    )

    assert retry.submission == first.submission
    assert conflict.accepted is False
    assert conflict.issues[0].code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_complex_orders_report_order_path_diagnostics() -> None:
    session = GameSession(_kernel(), _config())
    await session.start()

    result = await session.submit(
        "req_1",
        {"orders": [{"unit_id": "bob:unit_1", "action": "hold"}]},
        actor_id="alice",
        idempotency_key="invalid-unit",
    )

    assert result.accepted is False
    assert result.issues[0].code == "schema_invalid"
    assert list(result.issues[0].path) == ["orders", 0, "unit_id"]


@pytest.mark.asyncio
async def test_complex_orders_scripted_batch_replays_identically() -> None:
    summary = await run_scripted_session(_kernel(), _config(), _script(), seed=42)

    replayed = await replay_session(
        _kernel(),
        summary.config,
        summary.seed,
        summary.accepted_submissions,
        expected_trace=summary.comparable_trace,
    )

    assert replayed.matched is True


def _script() -> list[dict[str, Any]]:
    return [
        {
            "actor_id": "alice",
            "payload": {"orders": [{"unit_id": "alice:unit_1", "action": "move", "target": "center"}]},
            "idempotency_key": "alice-orders",
            "intent": "draft",
        },
        {
            "actor_id": "alice",
            "payload": {"orders": [{"unit_id": "alice:unit_1", "action": "hold"}]},
            "idempotency_key": "alice-final",
        },
        {
            "actor_id": "bob",
            "payload": {"orders": [{"unit_id": "bob:unit_1", "action": "hold"}]},
            "idempotency_key": "bob-orders",
        },
        {
            "actor_id": "carol",
            "payload": {"orders": [{"unit_id": "carol:unit_1", "action": "move", "target": "center"}]},
            "idempotency_key": "carol-orders",
        },
    ]


def _config() -> GameConfig:
    return GameConfig(
        players=[
            Player(id="alice", name="Alice"),
            Player(id="bob", name="Bob"),
            Player(id="carol", name="Carol"),
        ]
    )


def _kernel() -> RulesKernel:
    return cast(RulesKernel, ComplexOrdersKernel())