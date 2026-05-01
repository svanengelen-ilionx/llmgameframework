import pytest

from llmgames import Audience, GameConfig, GameSession, Player
from llmgames.games import HanabiLiteKernel
from llmgames.llm import build_prompt_context
from llmgames.testing import assert_projection_private, validate_kernel


def test_hanabi_lite_passes_kernel_validation() -> None:
    issues = validate_kernel(HanabiLiteKernel(), config=_config(), runs=6, max_steps=6)

    assert issues == []


@pytest.mark.asyncio
async def test_player_projection_hides_own_card_identities_but_reveals_others() -> None:
    session = GameSession(HanabiLiteKernel(), _config())
    await session.start()

    alice_projection = await session.projection(Audience.player("alice"))

    assert alice_projection.visible_state["own_hand"] == [
        {"slot": 0, "clues": []},
        {"slot": 1, "clues": []},
    ]
    assert alice_projection.visible_state["other_hands"] == {
        "bob": [{"color": "red", "rank": 2}, {"color": "blue", "rank": 2}]
    }
    assert_projection_private(
        alice_projection,
        forbidden_values=["r1a", "b1a"],
        context="Alice Hanabi projection",
    )


@pytest.mark.asyncio
async def test_llm_prompt_context_does_not_include_own_hidden_cards() -> None:
    session = GameSession(HanabiLiteKernel(), _config())
    await session.start()
    projection = await session.projection(Audience.llm("alice"))

    context = build_prompt_context(projection, projection.visible_requests[0])

    assert context.actor_id == "alice"
    assert context.visible_state["own_hand"] == [
        {"slot": 0, "clues": []},
        {"slot": 1, "clues": []},
    ]
    assert "r1a" not in str(context.model_dump(mode="json"))
    assert "b1a" not in str(context.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_hanabi_lite_clue_updates_only_public_knowledge() -> None:
    session = GameSession(HanabiLiteKernel(), _config())
    await session.start()

    result = await session.submit(
        "req_1",
        {"action": "clue", "target_id": "bob", "clue_type": "color", "value": "red"},
        actor_id="alice",
        idempotency_key="alice-clue-1",
    )
    bob_projection = await session.projection(Audience.player("bob"))

    assert result.accepted is True
    assert bob_projection.visible_state["own_hand"][0] == {
        "slot": 0,
        "clues": [{"type": "color", "value": "red"}],
    }
    assert "r2a" not in str(bob_projection.visible_state["own_hand"])


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])