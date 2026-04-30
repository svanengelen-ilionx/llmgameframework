import unittest

from llmgames.core.controllers import ScriptedController, intent
from llmgames.core.contracts import Player
from llmgames.core.engine import Engine, RunConfig
from llmgames.games import SplitOrSteal
from llmgames.llm import LLMController, LLMControllerConfig


class FakeProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("No fake LLM response left")
        return self.responses.pop(0)


class LLMControllerTests(unittest.TestCase):
    def test_one_llm_can_play_against_scripted_controller(self) -> None:
        provider = FakeProvider([
            '{"action": "ready", "input": {}}',
            '{"action": "choose_steal", "input": {}}',
        ])
        players = [Player("llm", "LLM"), Player("script", "Scripted")]
        controllers = {
            "llm": LLMController(provider),
            "script": ScriptedController([intent("ready"), intent("choose_split")]),
        }

        summary = Engine(SplitOrSteal(), RunConfig(players=players, controllers=controllers)).run()

        self.assertEqual(summary.result.scores, {"llm": 100, "script": 0})
        self.assertEqual(len(provider.prompts), 2)

    def test_two_llms_can_play_each_other(self) -> None:
        first_provider = FakeProvider([
            '{"action": "ready", "input": {}}',
            '{"action": "choose_split", "input": {}}',
        ])
        second_provider = FakeProvider([
            '{"action": "ready", "input": {}}',
            '{"action": "choose_split", "input": {}}',
        ])
        players = [Player("first", "First"), Player("second", "Second")]

        summary = Engine(
            SplitOrSteal(),
            RunConfig(
                players=players,
                controllers={
                    "first": LLMController(first_provider),
                    "second": LLMController(second_provider),
                },
            ),
        ).run()

        self.assertEqual(summary.result.scores, {"first": 50, "second": 50})

    def test_invalid_llm_output_is_retried(self) -> None:
        provider = FakeProvider([
            "not json",
            '{"action": "ready", "input": {}}',
        ])
        game = SplitOrSteal()
        state = game.create_initial_state([Player("llm", "LLM"), Player("other", "Other")])
        observation = game.get_observation(state, "llm")
        available_actions = game.get_available_actions(state, "llm")

        player_intent = LLMController(provider).get_intent(observation, available_actions)

        self.assertEqual(player_intent.action, "ready")
        self.assertEqual(len(provider.prompts), 2)
        self.assertIn("previous_error", provider.prompts[1])

    def test_invalid_llm_output_falls_back_deterministically(self) -> None:
        provider = FakeProvider(["not json"])
        game = SplitOrSteal()
        state = game.create_initial_state([Player("llm", "LLM"), Player("other", "Other")])
        observation = game.get_observation(state, "llm")
        available_actions = game.get_available_actions(state, "llm")

        player_intent = LLMController(
            provider,
            LLMControllerConfig(max_retries=0),
        ).get_intent(observation, available_actions)

        self.assertEqual(player_intent.action, "ready")
        self.assertEqual(player_intent.input, {})


if __name__ == "__main__":
    unittest.main()
