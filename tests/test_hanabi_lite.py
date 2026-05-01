import pytest
from typing import cast

from hypothesis import given, settings
from hypothesis import strategies as st

from llmgames import Audience, GameConfig, GameSession, Player, RulesKernel, card_option, hint_option
from llmgames.games import HanabiCard, HanabiLiteKernel
from llmgames.llm import build_prompt_context
from llmgames.testing import assert_projection_private, validate_kernel


def test_hanabi_lite_passes_kernel_validation() -> None:
    issues = validate_kernel(_runtime_kernel(), config=_config(), runs=6, max_steps=6)

    assert issues == []


def test_card_and_hint_option_helpers_mark_primitives() -> None:
    card = card_option("play:0", payload={"action": "play", "slot": 0}, slot=0, card_id="r1a")
    hint = hint_option(
        "clue:bob:color:red",
        payload={"action": "clue", "target_id": "bob", "clue_type": "color", "value": "red"},
        target_id="bob",
        clue_type="color",
    )

    assert card.metadata == {"primitive": "card", "slot": 0, "card_id": "r1a"}
    assert hint.metadata == {"primitive": "hint", "target_id": "bob", "clue_type": "color"}


@pytest.mark.asyncio
async def test_hanabi_lite_legal_options_use_card_and_hint_primitives() -> None:
    session = GameSession(_runtime_kernel(), _config())
    await session.start()

    legal_options = session.requests[0].legal_options
    assert legal_options is not None
    primitives = {option.metadata["primitive"] for option in legal_options.options}

    assert primitives == {"card", "hint"}


@pytest.mark.asyncio
async def test_player_projection_hides_own_card_identities_but_reveals_others() -> None:
    session = GameSession(_runtime_kernel(), _config())
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
    session = GameSession(_runtime_kernel(), _config())
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
    session = GameSession(_runtime_kernel(), _config())
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


@settings(max_examples=25)
@given(
    alice_card_ids=st.lists(
        st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=8),
        min_size=2,
        max_size=2,
        unique=True,
    )
)
def test_player_and_llm_projections_never_include_own_card_ids(alice_card_ids: list[str]) -> None:
    alice_card_ids = [f"secret-{card_id}" for card_id in alice_card_ids]
    kernel = HanabiLiteKernel()
    config = _config()
    state = kernel.initial_state(config, ctx=_ctx(config))
    for index, card_id in enumerate(alice_card_ids):
        state.hands["alice"][index].id = card_id

    player_projection = kernel.project_state(state, Audience.player("alice"), ctx=_ctx(config))
    llm_projection = kernel.project_state(state, Audience.llm("alice"), ctx=_ctx(config))

    player_data = player_projection.model_dump(mode="json")
    llm_data = llm_projection.model_dump(mode="json")
    assert all(not _contains_value(player_data, card_id) for card_id in alice_card_ids)
    assert all(not _contains_value(llm_data, card_id) for card_id in alice_card_ids)


@settings(max_examples=25)
@given(
    card_ids=st.lists(
        st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=8),
        min_size=4,
        max_size=4,
        unique=True,
    )
)
def test_public_projection_never_includes_any_hand_card_ids(card_ids: list[str]) -> None:
    card_ids = [f"secret-{card_id}" for card_id in card_ids]
    kernel = HanabiLiteKernel()
    config = _config()
    state = kernel.initial_state(config, ctx=_ctx(config))
    state.hands["alice"] = [
        HanabiCard(id=card_ids[0], color="red", rank=1),
        HanabiCard(id=card_ids[1], color="blue", rank=1),
    ]
    state.hands["bob"] = [
        HanabiCard(id=card_ids[2], color="red", rank=2),
        HanabiCard(id=card_ids[3], color="blue", rank=2),
    ]

    projection = kernel.project_state(state, Audience.public(), ctx=_ctx(config))
    projection_data = projection.model_dump(mode="json")

    assert all(not _contains_value(projection_data, card_id) for card_id in card_ids)


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])


def _runtime_kernel() -> RulesKernel:
    return cast(RulesKernel, HanabiLiteKernel())


def _ctx(config: GameConfig):
    from llmgames import RulesContext

    return RulesContext(config=config)


def _contains_value(container, value) -> bool:
    if container == value:
        return True
    if isinstance(container, dict):
        return any(_contains_value(item, value) for item in container.values())
    if isinstance(container, list):
        return any(_contains_value(item, value) for item in container)
    return False