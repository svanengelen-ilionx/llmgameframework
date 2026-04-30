# Game Authoring Agent Guide

This guide is written for AI agents that need to implement a new game on top of the `llmgames` framework. It is meant to be fetchable from GitHub and usable without reading `PLAN.MD`.

Fetch the raw guide from GitHub with:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/docs/game-authoring-agent-guide.md
```

Replace `<owner>` and `<repo>` with the actual GitHub repository coordinates. If the project uses a branch other than `main`, replace `main` as well.

## Goal

Create a complete, self-contained game project that is pleasant for a human end user to discover and start, while using `llmgames` as the game-engine framework.

A generated game should normally live outside the reusable framework package:

```text
games/
  my-game/
    README.md
    game.py
    run.py
    tests/
      test_game.py
    frontend/
      ... optional website frontend files ...
```

Use `llmgames/games/` only when adding a maintained built-in framework game. For most AI-authored games, keep the game backend, runner, tests, and optional frontend together under `games/<game-slug>/` so a human can start from one obvious folder.

The human end-user path should be clear from `games/<game-slug>/README.md`. The README must explain the game, the rules, and the exact command to run it locally.

## Files To Inspect First

Before implementing a game, inspect these files in the target repository:

- `llmgames/core/contracts.py`: public data contracts and protocols.
- `llmgames/core/authoring.py`: `BaseGameModule` and the `@action` decorator.
- `llmgames/core/engine.py`: engine loop, validation, limits, tracing, and result handling.
- `llmgames/core/controllers.py`: `ScriptedController` and `intent` test helper.
- `llmgames/core/schemas.py`: small reusable input schema helpers.
- `llmgames/core/views.py`: public/player view contracts.
- `llmgames/games/split_or_steal.py`: canonical built-in reference game.
- `tests/test_authoring.py`: minimal external game example using the public authoring API.
- `tests/test_split_or_steal.py`: scripted tests for the built-in reference game.

Do not depend on `PLAN.MD`; it is historical planning material.

## Required Game Folder

Create a game folder named with a lowercase kebab-case slug:

```text
games/<game-slug>/
```

Recommended contents:

```text
games/<game-slug>/
  README.md          # Human-facing rules and run instructions.
  game.py            # GameModule implementation.
  run.py             # One-command local runner for this game.
  tests/
    test_game.py     # ScriptedController tests for the game.
```

Optional contents:

```text
games/<game-slug>/
  frontend/          # Optional website frontend owned by this game.
  assets/            # Optional game-specific static assets.
```

The exact frontend structure is intentionally not prescribed by this guide. The backend must expose enough information through the framework contracts for an agent to design and implement an appropriate website autonomously.

## GameModule Contract

A game backend is a Python class that implements the `GameModule` protocol. The simplest path is to subclass `BaseGameModule` from `llmgames`.

A game module must provide:

- `get_info() -> GameInfo`
- `create_initial_state(players, seed) -> GameState`
- `get_observation(state, player_id) -> Observation`
- `get_result(state) -> GameResult`
- `is_terminal(state) -> bool`

A game module should usually also provide:

- `get_view(state, request) -> GameView` when a public or player-facing UI needs renderable state.
- `get_turn_order(state) -> Sequence[str]` when the default player order is not correct.

`BaseGameModule` provides:

- `actions`: a registry built from methods decorated with `@action`.
- `get_available_actions(state, player_id)`: filters registered actions using each action's `can_use` predicate.
- a default `get_turn_order` that reads `state.players`.
- a default `get_view` placeholder.

## Game State

Define game state in `game.py`. A dataclass is the preferred shape.

The state should include:

- `players: list[Player]`
- current phase or progress marker when the game has phases
- player choices, resources, scores, messages, or board state as needed
- deterministic limits such as max turns, max rounds, or max messages

Example shape:

```python
from dataclasses import dataclass, field
from llmgames import Player

@dataclass
class MyGameState:
    players: list[Player]
    phase: str = "playing"
    choices: dict[str, str] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
```

The engine stores the live state object. Action handlers may mutate this state directly and return `ActionResult(success=True, events=[...])`. `ActionResult.state_patch` is also supported by the engine for shallow field updates, but direct mutation is the common style in the current codebase.

## Game Info

`get_info` returns metadata used by runners, tests, and user interfaces:

```python
def get_info(self) -> GameInfo:
    return GameInfo(
        name="My Game",
        min_players=2,
        max_players=4,
        description="Short human-readable description.",
    )
```

The engine validates player count against `min_players` and `max_players` before the game starts.

## Initial State

`create_initial_state` receives the engine's players and optional seed:

```python
def create_initial_state(self, players: Sequence[Player], seed: int | None = None) -> MyGameState:
    return MyGameState(
        players=list(players),
        scores={player.id: 0 for player in players},
    )
```

Do not use system randomness here. If setup needs randomness, create deterministic state from the provided `seed` or store data that action handlers later randomize with `ActionContext.rng`.

## Observations

`get_observation` returns the state visible to one player/controller:

```python
def get_observation(self, state: MyGameState, player_id: str) -> Observation:
    return Observation(
        player_id=player_id,
        rules=self.rules,
        public={"phase": state.phase, "scores": dict(state.scores)},
        private={"your_choice": state.choices.get(player_id)},
        messages=[],
    )
```

Use observations for controller decisions, including LLM controllers. Observations should include:

- concise rules visible to the player
- public state needed to choose an action
- private player-specific state
- visible messages, if the game uses messaging

Do not leak another player's private information in `private` or `public` fields.

## Public And Player Views

`get_view` returns renderable state for UIs, traces, or external integrations. A frontend agent can use this method to understand what can be displayed without calling game internals.

Use `ViewRequest("public")` for public display state. If useful, support player-specific view requests by checking `request.player_id`.

Example:

```python
def get_view(self, state: MyGameState, request: ViewRequest) -> GameView:
    if request.name != "public":
        return super().get_view(state, request)
    return GameView(
        name="public",
        visibility="public",
        data={
            "phase": state.phase,
            "players": [player.id for player in state.players],
            "scores": dict(state.scores),
        },
    )
```

A website frontend should be able to derive display state from `get_view`, player-specific decision context from `get_observation`, legal controls from `get_available_actions`, input details from each action's `input_schema`, and final outcome from `GameResult`. This guide intentionally does not prescribe how to build that frontend.

## Actions

Actions are methods decorated with `@action`. Each action must define:

- stable action name
- human-readable description
- JSON-style input schema
- optional availability predicate through `can_use`
- handler method that returns `ActionResult`

Example:

```python
from llmgames import ActionContext, ActionResult, Event, action, empty_schema

@action(
    name="ready",
    description="Mark yourself ready.",
    input_schema=empty_schema(),
    can_use="_can_ready",
)
def _ready(
    self,
    state: MyGameState,
    player_id: str,
    input_value: dict[str, object],
    context: ActionContext,
) -> ActionResult:
    state.ready_players.add(player_id)
    return ActionResult(
        success=True,
        events=[Event("player_ready", f"{player_id} is ready", {"player_id": player_id})],
    )
```

The engine rejects:

- unknown action names
- unavailable actions
- inputs that do not match the action schema
- action results where `success` is false

## Input Schemas

Every action needs an input schema. Use `empty_schema()` for actions with no input.

For non-empty actions, use a JSON-schema-like object with:

- `type: "object"`
- `properties`
- `required` when fields are mandatory
- `additionalProperties: False`

Example:

```python
@action(
    name="send_message",
    description="Send a public message.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    can_use="_can_talk",
)
```

A frontend can use action names, descriptions, and input schemas to generate controls or validate input before submission. The backend remains authoritative.

## Availability Predicates

Use `can_use` to make actions phase-aware and player-aware.

Example:

```python
def _can_choose(self, state: MyGameState, player_id: str) -> bool:
    return state.phase == "choice" and player_id not in state.choices
```

Then attach it by name:

```python
@action(..., can_use="_can_choose")
```

Keep predicates pure: they should inspect state and return a boolean without mutating anything.

## Action Results And Events

Handlers return `ActionResult`.

Use successful results for legal transitions:

```python
return ActionResult(
    success=True,
    events=[Event("choice_submitted", f"{player_id} chose", {"player_id": player_id})],
)
```

Use failed results only for domain-level failures that should be reported as invalid intents by the engine:

```python
return ActionResult(success=False, error="choice was already submitted")
```

Prefer preventing illegal actions through `can_use` and input schemas. Use events for meaningful domain history: phase changes, submitted choices, messages, score resolution, or game end.

## Terminal Conditions And Results

`is_terminal` should be fast and deterministic:

```python
def is_terminal(self, state: MyGameState) -> bool:
    return state.phase == "end"
```

`get_result` should return `GameResult(is_terminal=False, ...)` while running, and a complete terminal result at the end:

```python
def get_result(self, state: MyGameState) -> GameResult:
    if not self.is_terminal(state):
        return GameResult(is_terminal=False, scores=dict(state.scores), reason="Game is still running")
    high_score = max(state.scores.values(), default=0)
    winners = [player_id for player_id, score in state.scores.items() if score == high_score]
    return GameResult(
        is_terminal=True,
        scores=dict(state.scores),
        winners=winners,
        reason="Game ended",
    )
```

Always make sure the game can terminate under scripted play and engine limits.

## Turn Order

By default, `BaseGameModule.get_turn_order` returns every `state.players` id in order. Override it if:

- only a subset of players should act in a phase
- the active player rotates
- the game needs a custom order

Example:

```python
def get_turn_order(self, state: MyGameState) -> Sequence[str]:
    if state.phase == "end":
        return []
    return [player.id for player in state.players]
```

## Messages

Use `Message` objects when the game has communication. Helpers are available from `llmgames`:

- `public_message`
- `private_message`
- `group_message`
- `visible_messages`

Store messages on state and expose appropriate messages through observations and views.

## Randomness

Do not import and use `random` directly in game logic. Use `ActionContext.rng` inside action handlers so runs can be reproduced with `RunConfig(seed=...)`.

Example:

```python
roll = context.rng.randint(1, 6)
```

## Runner Requirements

`run.py` should be the easiest way for a human to start the game from the game folder. It may run scripted players, a small CLI loop, or a local server if a frontend exists.

At minimum, it should:

- construct players
- construct controllers
- instantiate the game module
- run `Engine(game, RunConfig(...)).run()` or use `run_scripted_game`
- print the final result clearly

The README must show the exact command, for example:

```bash
python games/my-game/run.py
```

If the runner has optional dependencies, document setup commands in the game README.

## Tests

Add scripted tests under `games/<game-slug>/tests/test_game.py` or under the repository-level `tests/` folder with a clear game-specific name.

Test at least:

- a complete happy path that reaches a terminal result
- key scoring or outcome combinations
- invalid or unavailable actions are rejected
- the game terminates under scripted play
- important view or observation data if a frontend will depend on it

Use `ScriptedController` and `intent` for deterministic tests.

Example:

```python
from pathlib import Path
import sys

from llmgames import Engine, Player, RunConfig
from llmgames.core.controllers import ScriptedController, intent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import MyGame

players = [Player("alice", "Alice"), Player("bob", "Bob")]
summary = Engine(
    MyGame(),
    RunConfig(
        players=players,
        controllers={
            "alice": ScriptedController([intent("ready")]),
            "bob": ScriptedController([intent("ready")]),
        },
    ),
).run()
assert summary.result.is_terminal
```

## Frontend-Relevant Backend Information

A frontend implementation can derive these facts from the backend contracts:

- Game title, description, and player limits from `get_info()`.
- Public renderable state from `get_view(state, ViewRequest("public"))`.
- Player-specific renderable or decision state from `get_observation(state, player_id)`.
- Legal action list from `get_available_actions(state, player_id)`.
- Control names and labels from `ActionDefinition.name` and `ActionDefinition.description`.
- Input fields and validation rules from `ActionDefinition.input_schema`.
- Public history from `RunSummary.events` and trace events.
- Terminal display data from `GameResult.scores`, `GameResult.winners`, and `GameResult.reason`.

The frontend must treat the backend as authoritative for legal actions and results. It must not duplicate rules in a way that can diverge from the `GameModule`.

## What Not To Do

Do not:

- edit `llmgames/games/` unless creating a maintained built-in framework game
- make the human user hunt through framework internals to start the game
- skip `README.md` or omit exact run commands
- call LLM APIs from a `GameModule`
- let controllers mutate game state directly
- bypass the action registry to perform player moves
- use global mutable state for a game run
- use system randomness directly in game logic
- create unbounded loops inside game modules
- hide legal moves outside `get_available_actions`
- omit input schemas
- leak private player state through public observations or views
- build frontend behavior that is authoritative over backend rules
- make broad unrelated framework refactors while adding one game

## Implementation Checklist

Follow this checklist when creating a new game:

1. Read this guide and inspect the files listed in "Files To Inspect First".
2. Create `games/<game-slug>/`.
3. Write `games/<game-slug>/README.md` for a human end user.
4. Write `games/<game-slug>/game.py` with state, module class, actions, observations, views, terminal logic, and result logic.
5. Write `games/<game-slug>/run.py` with a clear local start path.
6. Add scripted tests.
7. If adding a frontend, keep it in `games/<game-slug>/frontend/` unless the existing repo already has a stronger convention.
8. Run the Python tests.
9. Run any game-specific or frontend verification commands.
10. Report changed files and verification results.

## Verification Commands

For the current Python-only framework, run:

```bash
python -m unittest discover -s tests
python -m unittest discover -s games/<game-slug>/tests
```

If the repository uses another test runner or a frontend build system, inspect project files and run the appropriate additional commands.
