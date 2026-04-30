import unittest
from collections.abc import Sequence
from dataclasses import dataclass, field

from llmgames import (
    ActionContext,
    ActionResult,
    BaseGameModule,
    Engine,
    Event,
    GameInfo,
    GameResult,
    Observation,
    Player,
    RunConfig,
    action,
    empty_schema,
    group_message,
    private_message,
    public_message,
    target_schema,
    visible_messages,
)
from llmgames.core.controllers import ScriptedController, intent
from llmgames.testing import assert_terminal, find_events, run_scripted_game


@dataclass
class TurnOrderState:
    players: list[Player]
    acted: list[str] = field(default_factory=list)


class BobOnlyGame(BaseGameModule):
    def get_info(self) -> GameInfo:
        return GameInfo(name="Bob Only", min_players=2, max_players=2)

    def create_initial_state(self, players: Sequence[Player], seed: int | None = None) -> TurnOrderState:
        return TurnOrderState(players=list(players))

    def get_turn_order(self, state: TurnOrderState) -> Sequence[str]:
        return [] if self.is_terminal(state) else ["bob"]

    def get_observation(self, state: TurnOrderState, player_id: str) -> Observation:
        return Observation(player_id=player_id, rules="Only Bob acts.")

    def get_result(self, state: TurnOrderState) -> GameResult:
        return GameResult(is_terminal=self.is_terminal(state))

    def is_terminal(self, state: TurnOrderState) -> bool:
        return bool(state.acted)

    @action(description="Act once.", input_schema=empty_schema())
    def act(
        self,
        state: TurnOrderState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        state.acted.append(player_id)
        return ActionResult(success=True)


@dataclass
class RollState:
    players: list[Player]
    rolls: list[int] = field(default_factory=list)


class RollGame(BaseGameModule):
    def get_info(self) -> GameInfo:
        return GameInfo(name="Roll", min_players=1, max_players=1)

    def create_initial_state(self, players: Sequence[Player], seed: int | None = None) -> RollState:
        return RollState(players=list(players))

    def get_observation(self, state: RollState, player_id: str) -> Observation:
        return Observation(player_id=player_id, rules="Roll once.")

    def get_result(self, state: RollState) -> GameResult:
        return GameResult(is_terminal=self.is_terminal(state), scores={"roller": state.rolls[0]} if state.rolls else {})

    def is_terminal(self, state: RollState) -> bool:
        return bool(state.rolls)

    @action(description="Roll.", input_schema=empty_schema())
    def roll(
        self,
        state: RollState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        value = context.rng.randint(1, 100)
        state.rolls.append(value)
        return ActionResult(success=True, events=[Event("rolled", "Rolled", {"value": value})])


class CoreHelperTests(unittest.TestCase):
    def test_engine_always_uses_game_turn_order(self) -> None:
        players = [Player("alice", "Alice"), Player("bob", "Bob")]
        summary = Engine(
            BobOnlyGame(),
            RunConfig(
                players=players,
                controllers={"alice": ScriptedController([]), "bob": ScriptedController([intent("act")])},
            ),
        ).run()

        self.assertEqual(summary.state.acted, ["bob"])

    def test_context_rng_is_seeded_deterministically(self) -> None:
        player = Player("roller", "Roller")
        scripts = {"roller": [intent("roll")]}

        first = run_scripted_game(RollGame(), [player], scripts, seed=42)
        second = run_scripted_game(RollGame(), [player], scripts, seed=42)

        self.assertEqual(first.result.scores, second.result.scores)
        self.assertEqual(find_events(first, "rolled")[0].data, find_events(second, "rolled")[0].data)
        assert_terminal(first)

    def test_message_visibility_helpers(self) -> None:
        messages = [
            public_message("system", "day starts", 0),
            private_message("system", "alice", "you are the seer", 0),
            group_message("system", ["alice", "bob"], "wolf chat", 0),
        ]

        self.assertEqual([message.text for message in visible_messages(messages, "alice")], [
            "day starts",
            "you are the seer",
            "wolf chat",
        ])
        self.assertEqual([message.text for message in visible_messages(messages, "carol")], ["day starts"])

    def test_schema_helpers(self) -> None:
        self.assertEqual(empty_schema()["properties"], {})
        self.assertEqual(target_schema()["required"], ["target_id"])


if __name__ == "__main__":
    unittest.main()
