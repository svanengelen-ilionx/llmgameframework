import unittest
from collections.abc import Sequence
from dataclasses import dataclass

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
)
from llmgames.core.controllers import ScriptedController, intent


@dataclass
class GuessState:
    players: list[Player]
    guesses: dict[str, int]


class GuessOneGame(BaseGameModule):
    def get_info(self) -> GameInfo:
        return GameInfo(name="Guess One", min_players=1, max_players=1)

    def create_initial_state(self, players: Sequence[Player], seed: int | None = None) -> GuessState:
        return GuessState(players=list(players), guesses={})

    def get_observation(self, state: GuessState, player_id: str) -> Observation:
        return Observation(player_id=player_id, rules="Guess the number 1.")

    def get_result(self, state: GuessState) -> GameResult:
        if not self.is_terminal(state):
            return GameResult(is_terminal=False)
        player_id = state.players[0].id
        score = 1 if state.guesses[player_id] == 1 else 0
        return GameResult(is_terminal=True, scores={player_id: score})

    def is_terminal(self, state: GuessState) -> bool:
        return len(state.guesses) == len(state.players)

    def _can_guess(self, state: GuessState, player_id: str) -> bool:
        return player_id not in state.guesses

    @action(
        description="Guess a number.",
        input_schema={
            "type": "object",
            "properties": {"number": {"type": "integer"}},
            "required": ["number"],
            "additionalProperties": False,
        },
        can_use="_can_guess",
    )
    def guess(
        self,
        state: GuessState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        raw_number = input_value["number"]
        if not isinstance(raw_number, int):
            return ActionResult(success=False, error="number must be an integer")
        number = raw_number
        state.guesses[player_id] = number
        return ActionResult(
            success=True,
            events=[Event("guess_made", f"{player_id} guessed", {"number": number})],
        )


class AuthoringTests(unittest.TestCase):
    def test_external_game_can_use_public_authoring_api(self) -> None:
        player = Player("author", "Author")
        game = GuessOneGame()

        summary = Engine(
            game,
            RunConfig(
                players=[player],
                controllers={"author": ScriptedController([intent("guess", number=1)])},
            ),
        ).run()

        self.assertEqual(summary.result.scores, {"author": 1})
        self.assertEqual(list(game.actions), ["guess"])


if __name__ == "__main__":
    unittest.main()
