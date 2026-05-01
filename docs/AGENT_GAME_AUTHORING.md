# llmgames Agent Game Authoring Instructions

Use this document as the single implementation guide when an autonomous AI coding agent is asked to create a game with the `llmgames` Python package.

## Role

You are an autonomous AI coding agent implementing one game in the user's project. You are using `llmgames` as an installed Python package.

You are not building a game engine. You are not modifying `llmgames` core. You are writing a game kernel, a small test suite, and any project-local glue the user requested.

## Hard Rules

- Install or import `llmgames` as a package; do not require pulling the full `llmgames` repository to implement a game.
- Do not edit files inside the `llmgames` package unless the user explicitly asks you to work on the framework itself.
- Use public authoring imports from `llmgames`, `llmgames.testing`, and, for LLM-player tests, `llmgames.responders`.
- Create game files in the user's project, for example `generated_games/<game_id>.py` and `tests/test_<game_id>.py`.
- Run validation and tests before reporting completion.
- If the package lacks a general capability needed by the game, report the missing capability and a workaround; do not patch the framework as part of game generation.

## Install

If `llmgames` is published in the user's environment:

```bash
python -m pip install llmgames
python -m pip install pytest pytest-asyncio
```

If the user gives a GitHub package URL instead of a published package, install it directly:

```bash
python -m pip install 'llmgames @ git+https://github.com/<owner>/<repo>.git'
python -m pip install pytest pytest-asyncio
```

Do not clone or inspect the framework repository unless the user explicitly requests framework changes. The instructions in this document and the installed package API are the contract.

## Mental Model

- `RulesKernel`: synchronous, deterministic game rules supplied by the game author.
- `GameSession`: async runtime that owns request IDs, submission IDs, event order, projections, replay, deadlines, and idempotency.
- `RequestSpec`: author-facing request returned by `current_requests()`.
- `InteractionRequest`: runtime-managed request passed back into validation and resolution.
- `Submission`: player, LLM, script, timer, or replay action submitted to a request.
- `TransitionResult`: result of applying accepted final submissions to truth state.
- `StateProjection`: audience-visible state produced by the kernel.
- `validate_kernel()`: authoring harness that catches common kernel contract mistakes.
- `run_scripted_session()` and `replay_session()`: deterministic end-to-end checks.
- `LLMResponder`: submits an LLM player's payload through the same runtime path as humans.

## Files To Create

Prefer this layout when the user's project has no existing convention:

```text
generated_games/<game_id>.py
tests/test_<game_id>.py
```

If the project already has a source layout, follow it, for example:

```text
src/<project>/games/<game_id>.py
tests/test_<game_id>.py
```

Do not place generated game code inside the installed `llmgames` package.

## Public Imports

Use these imports for game code:

```python
from pydantic import BaseModel, ConfigDict, Field

from llmgames import (
    Audience,
    GameConfig,
    GameEventSpec,
    GameResult,
    InteractionRequest,
    LegalOption,
    LegalOptions,
    Message,
    Player,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
    approval_option,
    card_option,
    hint_option,
    order_set_option,
)
```

Use these imports for tests:

```python
from llmgames import Audience, GameConfig, GameSession, Player
from llmgames.testing import assert_projection_private, replay_session, run_scripted_session, validate_kernel
from llmgames.responders import FakeLLMProvider, LLMResponder
```

For LLM privacy tests, this import is allowed:

```python
from llmgames.llm import build_prompt_context
```

## Kernel Skeleton

Start from this shape and adapt it to the requested game:

```python
from pydantic import BaseModel, Field

from llmgames import (
    Audience,
    GameConfig,
    InteractionRequest,
    LegalOptions,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)


class GeneratedState(BaseModel):
    turn_number: int = 1
    phase: str = "planning"
    submitted_player_ids: list[str] = Field(default_factory=list)
    resolved: bool = False


class GeneratedKernel:
    game_id = "generated_game"
    state_model = GeneratedState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> GeneratedState:
        return GeneratedState()

    def current_requests(self, state: GeneratedState, ctx: RulesContext) -> list[RequestSpec]:
        if state.resolved:
            return []
        return [
            RequestSpec(
                key=f"act:{player.id}:turn_{state.turn_number}",
                kind="act",
                actor_id=player.id,
                mode="barrier",
                input_schema={
                    "type": "object",
                    "properties": {"action": {"type": "string", "enum": ["hold"]}},
                    "required": ["action"],
                    "additionalProperties": False,
                },
                legal_options=LegalOptions(kind="choice", examples=[{"action": "hold"}]),
            )
            for player in ctx.config.players
        ]

    def validate_submission(
        self,
        state: GeneratedState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        if request.actor_id is not None and submission.actor_id != request.actor_id:
            return [ValidationIssue(code="wrong_actor", message="Only the requested player may act.", path=["actor_id"])]
        return []

    def resolve(
        self,
        state: GeneratedState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        new_state = state.model_copy(deep=True)
        for submission in submissions:
            if submission.actor_id and submission.actor_id not in new_state.submitted_player_ids:
                new_state.submitted_player_ids.append(submission.actor_id)
        if len(new_state.submitted_player_ids) < len(ctx.config.players):
            return TransitionResult(new_state=new_state)
        new_state.resolved = True
        return TransitionResult(
            new_state=new_state,
            events=[GameEventSpec(kind="turn_resolved", payload={"turn_number": state.turn_number})],
            resolved_request_keys=[request.spec_key for request in requests],
        )

    def project_state(self, state: GeneratedState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(
            phase="complete" if state.resolved else state.phase,
            visible_state={
                "turn_number": state.turn_number,
                "phase": state.phase,
                "submitted_player_ids": sorted(state.submitted_player_ids),
                "resolved": state.resolved,
            },
        )
```

## Design Workflow

1. Identify players, phases, hidden information, actions, end condition, and which players are LLM-controlled.
2. Define the Pydantic truth-state model.
3. Define one or more `RequestSpec` objects for every active phase.
4. Add `input_schema` and `legal_options` examples that are directly submittable.
5. Implement `validate_submission()` with actionable `ValidationIssue` paths and hints.
6. Implement `resolve()` using `state.model_copy(deep=True)`.
7. Implement `project_state()` for public, player, and LLM audiences.
8. Write validation, replay, invalid-submission, privacy, and LLM-player tests.
9. Run tests, fix the generated game, and repeat until green.

## Player Experience Requirements

Design both rules and interaction affordances. The end user should receive a game that is pleasant to play or render.

Every generated game should expose enough visible state for a UI or chat interface to explain:

- the current phase and turn number
- who can act now
- what each visible player can do
- what has happened so far
- what remains hidden
- why a submitted action failed
- how the game ended

Use clear phase names, stable IDs, and human-readable labels. Keep payloads machine-readable and deterministic.

Good legal option shape:

```python
LegalOption(
    value="move:north_gate",
    label="Move the scout to North Gate",
    payload={"orders": [{"unit_id": "scout_1", "action": "move", "target": "north_gate"}]},
    metadata={"target_label": "North Gate"},
)
```

Bad validation issue:

```python
ValidationIssue(code="invalid", message="Invalid move")
```

Good validation issue:

```python
ValidationIssue(
    code="invalid_target",
    message="Move orders must target an adjacent district.",
    path=["payload", "orders", 0, "target"],
    hint="Choose one of the target district IDs listed in legal_options.",
)
```

## Recipes

### Simultaneous Barrier Requests

Use `mode="barrier"` and one stable request key per actor. In `resolve()`, return unchanged or partially updated state until enough final submissions are present. Resolve all involved request keys once the batch is complete.

### Draft And Final Submissions

Draft submissions use `intent="draft"`. They are accepted and recorded but do not trigger `resolve()`. Final submissions use the default `intent="final"` and are passed to `resolve()`.

Tests should prove drafts can be revised and final submissions resolve the batch.

### Hidden Information

Declare private paths in `model_config` and keep hidden truth out of unauthorized projections:

```python
class HiddenState(BaseModel):
    secret_roles: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(json_schema_extra={
        "private_paths": ["secret_roles"],
        "private_paths_by_audience": {
            "player": ["secret_roles.{audience.player_id}"],
            "llm": ["secret_roles.{audience.player_id}"],
        },
    })
```

Use `Audience.llm(player_id)` in tests to prove LLM players see enough to act but not hidden truth they should not know.

### LLM Players

LLM players submit through the same runtime path as humans. Use fake providers for deterministic tests:

```python
provider = FakeLLMProvider({request.spec_key: legal_payload})
responder = LLMResponder(provider)
result = await responder.submit_for_request(session, request)
assert result.accepted is True
assert result.submission.source == "llm"
```

Legal options and examples are the main way to make LLM actions reliable.

### Timers And Deadlines

Use `mode="timer"` and set `deadline_at` on `RequestSpec` when the requested game needs timeouts. In tests, use `ManualClock` with `GameSession(..., clock=clock)` so timeout behavior is deterministic.

### Nested Order Sets

Use nested payloads for medium-complexity actions. Prefer `order_set_option()` for order-like payloads and include concrete examples:

```python
LegalOptions(
    kind="order_set",
    options=[order_set_option(
        "hold",
        label="Hold position",
        payload={"orders": [{"unit_id": "unit_1", "action": "hold"}]},
        order_count=1,
        subject_ids=["unit_1"],
    )],
    examples=[{"orders": [{"unit_id": "unit_1", "action": "hold"}]}],
)
```

## Required Tests

### Kernel Validation

```python
def test_generated_kernel_validates() -> None:
    assert validate_kernel(GeneratedKernel(), config=_config(), runs=3) == []
```

### Scripted Replay

```python
@pytest.mark.asyncio
async def test_generated_game_replays() -> None:
    summary = await run_scripted_session(GeneratedKernel(), _config(), _script(), seed=42)
    replayed = await replay_session(
        GeneratedKernel(),
        summary.config,
        summary.seed,
        summary.accepted_submissions,
        expected_trace=summary.comparable_trace,
    )
    assert replayed.matched is True
```

### Invalid Submission Diagnostics

```python
@pytest.mark.asyncio
async def test_generated_game_reports_invalid_nested_payload() -> None:
    session = GameSession(GeneratedKernel(), _config())
    await session.start()
    result = await session.submit("req_1", {"orders": [{"bad": True}]}, actor_id="alice", idempotency_key="bad")
    assert result.accepted is False
    assert result.issues[0].path
    assert result.issues[0].hint is not None
```

### LLM Player

```python
@pytest.mark.asyncio
async def test_llm_player_acts_from_visible_request() -> None:
    session = GameSession(GeneratedKernel(), _config())
    await session.start()
    request = next(req for req in session.requests if req.actor_id == "bot")
    responder = LLMResponder(FakeLLMProvider({request.spec_key: _legal_payload_for_bot()}))

    result = await responder.submit_for_request(session, request)

    assert result.accepted is True
    assert result.submission.source == "llm"
```

### LLM Privacy

If the game has hidden information:

```python
projection = await session.projection(Audience.llm("bot"))
context = build_prompt_context(projection, projection.visible_requests[0])
assert "secret-role-value" not in str(context.visible_state)
assert "secret-role-value" not in str(context.visible_messages)
```

## Failure Recovery

- If `validate_kernel()` fails, fix the generated game, not `llmgames`.
- If replay diverges, inspect `replayed.first_difference` and make request keys, events, and state updates deterministic.
- If an LLM payload is rejected, improve `legal_options`, examples, or `validate_submission()` diagnostics.
- If privacy tests fail, change `project_state()` or private path metadata.
- If a request is ambiguous in a script, use `request_spec_key` in the scripted submission.
- If a framework capability is missing, report the missing general capability and a workaround instead of editing core.

## Done Criteria

- The generated game imports cleanly.
- The generated game uses public `llmgames` APIs.
- `validate_kernel()` returns no issues.
- Scripted replay matches.
- Invalid submissions return helpful `ValidationIssue` paths and hints.
- At least one LLM player test uses `FakeLLMProvider` and `LLMResponder`.
- Hidden information, if present, is protected from unauthorized player and LLM audiences.
- The project test suite passes.
- The final response tells the user where the generated game and tests were created and how to run them.
