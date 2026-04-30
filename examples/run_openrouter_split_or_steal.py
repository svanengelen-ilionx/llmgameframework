from llmgames.core.controllers import ScriptedController, intent
from llmgames.core.contracts import Player
from llmgames.core.engine import Engine, RunConfig
from llmgames.games import SplitOrSteal
from llmgames.llm import LLMController, OpenRouterProvider


def main() -> None:
    players = [Player("llm", "OpenRouter"), Player("script", "Scripted")]
    controllers = {
        "llm": LLMController(OpenRouterProvider.from_env()),
        "script": ScriptedController([intent("ready"), intent("choose_split")]),
    }
    summary = Engine(SplitOrSteal(), RunConfig(players=players, controllers=controllers)).run()
    print(summary.result)


if __name__ == "__main__":
    main()
