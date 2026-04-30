from llmgames.core.controllers import ScriptedController, intent
from llmgames.core.contracts import Player
from llmgames.core.engine import Engine, RunConfig
from llmgames.games import SplitOrSteal


def main() -> None:
    players = [Player("alice", "Alice"), Player("bob", "Bob")]
    controllers = {
        "alice": ScriptedController([intent("ready"), intent("choose_split")]),
        "bob": ScriptedController([intent("ready"), intent("choose_steal")]),
    }
    summary = Engine(SplitOrSteal(), RunConfig(players=players, controllers=controllers)).run()
    print(summary.result)


if __name__ == "__main__":
    main()
