from __future__ import annotations

from collections.abc import Iterable, Mapping

from llmgames.core.contracts import GameModule, Player, PlayerIntent
from llmgames.core.controllers import ScriptedController
from llmgames.core.engine import Engine, RunConfig, RunSummary


def run_scripted_game(
    game: GameModule,
    players: Iterable[Player],
    scripts: Mapping[str, Iterable[PlayerIntent]],
    *,
    seed: int | None = None,
    max_turns: int = 100,
    max_actions: int = 500,
) -> RunSummary:
    player_list = list(players)
    controllers = {player_id: ScriptedController(intents) for player_id, intents in scripts.items()}
    return Engine(
        game,
        RunConfig(
            players=player_list,
            controllers=controllers,
            seed=seed,
            max_turns=max_turns,
            max_actions=max_actions,
        ),
    ).run()


def assert_terminal(summary: RunSummary) -> None:
    if not summary.result.is_terminal:
        raise AssertionError("Expected game to be terminal")


def find_events(summary: RunSummary, event_type: str):
    return [event for event in summary.events if event.type == event_type]
