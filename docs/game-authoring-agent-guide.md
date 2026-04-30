# Game Authoring Agent Guide

This guide is written for AI agents that need to implement a new game on top of the `llmgames` framework.

Fetch the raw guide from GitHub with:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/docs/game-authoring-agent-guide.md
```

Replace `<owner>` and `<repo>` with the actual GitHub repository coordinates. If the project uses a branch other than `main`, replace `main` as well.

## Goal

Create a complete, standalone game project that is pleasant for a human end user to discover and start, while using `llmgames` as an installed framework dependency.

A generated game should not require the human user to clone or edit the `llmgames` framework repository. The agent should create a new project folder for the game and install `llmgames` from GitHub.

For example, a prompt like this should be enough:

```text
Make a rock-paper-scissors game using this guide: https://raw.githubusercontent.com/<owner>/<repo>/main/docs/game-authoring-agent-guide.md. It should be two AIs fighting each other and it should be shown on a website hosted locally.
```

The expected result is a local game project similar to:

```text
rock-paper-scissors/
    README.md
    pyproject.toml
    game.py
    run.py
    tests/
        test_game.py
    frontend/
        ... optional website frontend files ...
```

Use the `llmgames` repository itself only when changing the framework or adding a maintained built-in framework game. For normal AI-authored games, keep the game backend, runner, tests, and optional frontend together in the standalone game project.

The human end-user path should be clear from `README.md`. The README must explain the game, the rules, setup, and the exact command to run it locally.

## Dependency Setup

`llmgames` is not assumed to be published to PyPI. Add it as a direct GitHub dependency in the generated game's `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "rock-paper-scissors"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "llmgames @ git+https://github.com/<owner>/<repo>.git@main",
]
```

Replace `<owner>`, `<repo>`, and `main` with the same repository coordinates used for the raw guide URL.

The README should include setup commands like:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## Framework Files To Inspect

Before implementing a game, inspect these framework files. The agent may inspect them from the installed `llmgames` package, from a temporary dependency checkout created by the package manager, or from GitHub raw URLs. The human-facing game project does not need to be inside the `llmgames` repository.

- `llmgames/core/contracts.py`: public data contracts and protocols.
- `llmgames/core/authoring.py`: `BaseGameModule` and the `@action` decorator.
- `llmgames/core/engine.py`: engine loop, validation, limits, tracing, and result handling.
- `llmgames/core/controllers.py`: `ScriptedController` and `intent` test helper.
- `llmgames/core/schemas.py`: small reusable input schema helpers.
- `llmgames/core/views.py`: public/player view contracts.
- `llmgames/testing.py`: scripted-game test helpers.
- `llmgames/games/split_or_steal.py`: canonical built-in reference game.
- `tests/test_authoring.py`: minimal external game example using the public authoring API.
- `tests/test_split_or_steal.py`: scripted tests for the built-in reference game.

Some built-in framework files use internal import paths such as `llmgames.core.contracts`. Generated standalone games should prefer the imports shown in the next section unless a name is documented there as requiring an internal path.

## Import Reference

The top-level `llmgames` package exports the stable authoring and runtime names most games need:

```python
from llmgames import (
    ActionContext,
    ActionResult,
    BaseGameModule,
    Engine,
    Event,
    GameInfo,
    GameResult,
    GameView,
    Message,
    Observation,
    Player,
    RunConfig,
    ViewRequest,
    action,
    empty_schema,
    group_message,
    private_message,
    public_message,
    target_schema,
    visible_messages,
)
```

`RunSummary` and engine exceptions are not top-level exports. Import them from `llmgames.core.engine` when annotating summaries or asserting engine errors in tests:

```python
from llmgames.core.engine import EngineError, InvalidIntentError, LimitExceededError, RunSummary
```

Scripted controller helpers are not top-level exports. Import them from their module:

```python
from llmgames.core.controllers import ScriptedController, intent
```

Testing convenience helpers are available from `llmgames.testing`:

```python
from llmgames.testing import assert_terminal, find_events, run_scripted_game
```

## Required Project Folder

Create a standalone project folder named with a lowercase kebab-case slug:

```text
<game-slug>/
```

Recommended contents:

```text
<game-slug>/
    README.md          # Human-facing rules and run instructions.
    pyproject.toml     # Installs llmgames from GitHub.
    game.py            # GameModule implementation.
    run.py             # One-command local runner for this game.
    tests/
        test_game.py     # ScriptedController tests for the game.
```

Optional contents:

```text
<game-slug>/
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

The engine stores the live state object. Action handlers may mutate this state directly and return `ActionResult(success=True, events=[...])`. This is the common style in the current codebase.

`ActionResult.state_patch` is also supported, but only for shallow field updates: the engine calls `.update()` for dict states and `setattr(state, key, value)` for object states. Do not use `state_patch` for nested updates or complex state transitions. Do not combine `state_patch` with frozen dataclass state; `setattr` will fail on frozen instances.

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
class MyGame(BaseGameModule):
    rules = "Describe the rules visible to every player."

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

These rejections are fatal for the current run: the engine raises `InvalidIntentError` and `Engine.run()` does not return a normal `RunSummary`. Prevent routine illegal moves with `can_use` predicates and input schemas instead of returning `ActionResult(success=False)` from handlers.

## Input Schemas

Every action should have an input schema. If `input_schema` is omitted, `@action` defaults to an empty object schema, but explicit schemas are clearer for agents and frontends. Use `empty_schema()` for actions with no input.

For non-empty actions, use a JSON-schema-like object with:

- `type: "object"`
- `properties`
- `required` when fields are mandatory
- `additionalProperties: False`

Input validation is intentionally small and flat. The top-level action input must be an object. Field validation currently supports `type: "string"`, `type: "integer"`, `type: "boolean"`, `enum`, `minLength`, and `maxLength`. Nested object schemas, arrays, numbers, and null values are not deeply validated by the framework. If a game needs additional constraints, validate them inside the handler after the schema passes.

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

For actions that target another player, `target_schema()` is available from the top-level package:

```python
@action(
    name="challenge",
    description="Challenge another player.",
    input_schema=target_schema(),
    can_use="_can_challenge",
)
```

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

Reserve failed results for unrecoverable domain failures that should terminate the run as invalid intents:

```python
return ActionResult(success=False, error="choice was already submitted")
```

This aborts the run with `InvalidIntentError`. Prefer preventing illegal actions through `can_use` and input schemas. Use events for meaningful domain history: phase changes, submitted choices, messages, score resolution, or game end.

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

`ActionResult.messages` is currently not consumed by the engine. Returning `messages=[...]` does not store, route, trace, or expose messages by itself. If a message should affect the game or UI, append it to game state in the handler, then include it in observations and views. Returning the same message in `ActionResult.messages` is optional metadata only.

## Randomness

Do not import and use `random` directly in game logic. Use `ActionContext.rng` inside action handlers so runs can be reproduced with `RunConfig(seed=...)`.

Example:

```python
roll = context.rng.randint(1, 6)
```

## Runner Requirements

`run.py` should be the easiest way for a human to start the game from the project folder. It may run scripted players, AI players, a small CLI loop, or a local server if a frontend exists.

At minimum, it should:

- construct players
- construct controllers
- instantiate the game module
- run `Engine(game, RunConfig(...)).run()` or use `run_scripted_game`
- print the final result clearly

If using `run_scripted_game`, import it explicitly:

```python
from llmgames.testing import run_scripted_game
```

The README must show the exact command, for example:

```bash
python run.py
```

If the user asks for AI players, configure controllers using the available `llmgames` controller and LLM provider APIs. If real model calls require credentials, document the required environment variables and provide a deterministic fallback or scripted demo path so the project can still be verified locally.

If the user asks for a locally hosted website, provide a local web start command and URL in the README. The guide does not prescribe the frontend stack, but the finished project must let the human start the website from the standalone project folder.

If the runner has optional dependencies, document setup commands in the README.

## Event Streaming And Tracing

For live integrations, pass `on_event` to `RunConfig`. The callback receives each domain `Event` synchronously as the engine applies successful action results:

```python
streamed_events: list[Event] = []
summary = Engine(
    game,
    RunConfig(players=players, controllers=controllers, on_event=streamed_events.append),
).run()
```

Use `on_event` for simple real-time updates to a local server or frontend adapter. Use `RunSummary.events` after the run for the final domain event list. Use `RunSummary.trace_events` or a `RunConfig(recorder=...)` when a frontend or debug tool needs lower-level engine trace data such as turns, available actions, intents, and emitted views.

## Tests

Add tests under `tests/test_game.py` in the standalone game project.

Test at least:

- a complete happy path that reaches a terminal result
- key scoring or outcome combinations
- invalid or unavailable actions are rejected
- the game terminates under scripted play
- important view or observation data if a frontend will depend on it

Use `ScriptedController` and `intent` for deterministic tests.

Use `llmgames.testing` helpers to reduce boilerplate when useful:

```python
from llmgames.testing import assert_terminal, find_events, run_scripted_game
```

- `run_scripted_game(game, players, scripts, *, seed=None, max_turns=100, max_actions=500) -> RunSummary`: runs a game with `ScriptedController`s built from each player's intent script.
- `assert_terminal(summary) -> None`: raises `AssertionError` if the run did not end in a terminal result.
- `find_events(summary, event_type) -> list[Event]`: returns domain events from the summary matching the given type.

Example using the helper:

```python
from llmgames import Player
from llmgames.core.controllers import intent
from llmgames.testing import assert_terminal, find_events, run_scripted_game

from game import MyGame

players = [Player("alice", "Alice"), Player("bob", "Bob")]
summary = run_scripted_game(
    MyGame(),
    players,
    {
        "alice": [intent("ready")],
        "bob": [intent("ready")],
    },
)
assert_terminal(summary)
assert find_events(summary, "player_ready")
```

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

When a user requests a locally hosted website, the agent should choose an appropriate frontend and local server approach for the standalone project. The website should use backend-derived game state, legal actions, action schemas, events, and results. The README must include the command to start it and the local URL to open.

## What Not To Do

Do not:

- require the human user to clone the `llmgames` repository just to create or run a game
- edit the `llmgames` framework unless the user explicitly asks to change the framework itself
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

1. Read this guide and inspect the framework files listed above.
2. Create a standalone `<game-slug>/` project folder.
3. Write `<game-slug>/pyproject.toml` with the GitHub `llmgames` dependency.
4. Write `<game-slug>/README.md` for a human end user.
5. Write `<game-slug>/game.py` with state, module class, actions, observations, views, terminal logic, and result logic.
6. Write `<game-slug>/run.py` with a clear local start path.
7. If the user asks for AI players, wire controllers to the available LLM/provider APIs or document required credentials and provide a verifiable fallback.
8. If the user asks for a local website, add frontend/server files in the standalone project and document one start command plus the local URL.
9. Add tests under `<game-slug>/tests/`.
10. Run the Python tests.
11. Run any game-specific or frontend verification commands.
12. Report changed files, setup commands, start commands, local URLs, and verification results.

## Verification Commands

For a standalone Python game project, run from the project root:

```bash
python -m unittest discover -s tests
```

If the standalone project uses another test runner or a frontend build system, inspect project files and run the appropriate additional commands.
