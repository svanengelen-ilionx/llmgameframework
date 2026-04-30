import unittest

from llmgames.core.controllers import ScriptedController, intent
from llmgames.core.contracts import Event, Player
from llmgames.core.engine import Engine, InvalidIntentError, RunConfig
from llmgames.games import SplitOrSteal


class SplitOrStealTests(unittest.TestCase):
    def test_both_split(self) -> None:
        summary = self.run_game("choose_split", "choose_split")

        self.assertTrue(summary.result.is_terminal)
        self.assertEqual(summary.result.scores, {"alice": 50, "bob": 50})
        self.assertEqual(summary.state.phase, "end")

    def test_alice_steals_bob_splits(self) -> None:
        summary = self.run_game("choose_steal", "choose_split")

        self.assertEqual(summary.result.scores, {"alice": 100, "bob": 0})
        self.assertEqual(summary.result.winners, ["alice"])

    def test_alice_splits_bob_steals(self) -> None:
        summary = self.run_game("choose_split", "choose_steal")

        self.assertEqual(summary.result.scores, {"alice": 0, "bob": 100})
        self.assertEqual(summary.result.winners, ["bob"])

    def test_both_steal(self) -> None:
        summary = self.run_game("choose_steal", "choose_steal")

        self.assertEqual(summary.result.scores, {"alice": 0, "bob": 0})
        self.assertEqual(summary.result.winners, [])

    def test_invalid_action_is_rejected(self) -> None:
        engine = Engine(
            SplitOrSteal(),
            RunConfig(
                players=self.players(),
                controllers={
                    "alice": ScriptedController([intent("dance")]),
                    "bob": ScriptedController([intent("ready")]),
                },
            ),
        )

        with self.assertRaisesRegex(InvalidIntentError, "Unknown action"):
            engine.run()

    def test_invalid_input_is_rejected(self) -> None:
        engine = Engine(
            SplitOrSteal(),
            RunConfig(
                players=self.players(),
                controllers={
                    "alice": ScriptedController([intent("send_message")]),
                    "bob": ScriptedController([intent("ready")]),
                },
            ),
        )

        with self.assertRaisesRegex(InvalidIntentError, "Missing required"):
            engine.run()

    def test_events_can_be_streamed_while_running(self) -> None:
        streamed_events: list[Event] = []
        players = self.players()
        controllers = {
            "alice": ScriptedController([intent("ready"), intent("choose_split")]),
            "bob": ScriptedController([intent("ready"), intent("choose_steal")]),
        }

        summary = Engine(
            SplitOrSteal(),
            RunConfig(players=players, controllers=controllers, on_event=streamed_events.append),
        ).run()

        self.assertEqual(streamed_events, summary.events)
        self.assertEqual(streamed_events[-1].type, "game_resolved")
        self.assertEqual(streamed_events[-1].data["choices"], {"alice": "split", "bob": "steal"})

    def run_game(self, alice_choice: str, bob_choice: str):
        players = self.players()
        controllers = {
            "alice": ScriptedController([intent("ready"), intent(alice_choice)]),
            "bob": ScriptedController([intent("ready"), intent(bob_choice)]),
        }
        return Engine(SplitOrSteal(), RunConfig(players=players, controllers=controllers)).run()

    def players(self) -> list[Player]:
        return [Player("alice", "Alice"), Player("bob", "Bob")]


if __name__ == "__main__":
    unittest.main()
