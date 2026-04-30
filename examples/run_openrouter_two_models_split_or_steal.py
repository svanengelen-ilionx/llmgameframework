import os

from llmgames.core.contracts import Event, Player
from llmgames.core.engine import Engine, RunConfig
from llmgames.games import SplitOrSteal
from llmgames.llm import LLMController, OpenRouterConfig, OpenRouterProvider


def main() -> None:
    alice_model = _required_env("OPENROUTER_ALICE_MODEL")
    bob_model = _required_env("OPENROUTER_BOB_MODEL")
    players = [Player("alice", f"Alice ({alice_model})"), Player("bob", f"Bob ({bob_model})")]
    controllers = {
        "alice": LLMController(OpenRouterProvider(OpenRouterConfig(model=alice_model))),
        "bob": LLMController(OpenRouterProvider(OpenRouterConfig(model=bob_model))),
    }

    print("Split or Steal: Alice vs Bob")
    print(f"Alice model: {alice_model}")
    print(f"Bob model:   {bob_model}")
    print()

    summary = Engine(
        SplitOrSteal(),
        RunConfig(players=players, controllers=controllers, on_event=print_event),
    ).run()

    print()
    print("Final result")
    print(f"Scores: {summary.result.scores}")
    print(f"Winners: {summary.result.winners or 'none'}")


def print_event(event: Event) -> None:
    if event.type == "message_sent":
        print(f"[{event.data['player_id']}] {event.data['text']}")
        return
    if event.type == "player_ready":
        print(f"[{event.data['player_id']}] ready")
        return
    if event.type == "choice_phase_started":
        print("Choice phase started")
        return
    if event.type == "choice_submitted":
        print(f"[{event.data['player_id']}] submitted a choice")
        return
    if event.type == "game_resolved":
        print(f"Choices: {event.data['choices']}")
        print(f"Scores: {event.data['scores']}")
        return
    print(event.message)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    main()
