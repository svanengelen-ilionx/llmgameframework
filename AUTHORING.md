# Authoring Games With llmgames

This guide is the context to give an LLM when asking it to generate a game with `llmgames`.

## Core Rule

Generated games should import public contracts from `llmgames` and test helpers from `llmgames.testing`. Do not import from internal modules such as `llmgames.runtime`, `llmgames.models`, or `llmgames.validation` in generated game code unless the test explicitly allows it.

## What A Game Implements

A game implements a synchronous rules kernel with these attributes and methods:

- `game_id: str`
- `state_model: type[BaseModel]`
- `initial_state(config, ctx) -> StateModel`
- `current_requests(state, ctx) -> list[RequestSpec]`
- `validate_submission(state, request, submission, ctx) -> list[ValidationIssue]`
- `resolve(state, requests, submissions, ctx) -> TransitionResult`
- `project_state(state, audience, ctx) -> StateProjection`

Kernel methods must be deterministic and must not mutate their input `state`, `request`, or `submission` objects. Use `state.model_copy(deep=True)` in `resolve()` before applying accepted submissions.

## State Model

Use a Pydantic `BaseModel` for truth state:

```python
class GameState(BaseModel):
    turn_number: int = 1
    scores: dict[str, int] = Field(default_factory=dict)
```

For hidden information, declare private paths in `model_config`:

```python
class GameState(BaseModel):
    secret_hands: dict[str, list[str]] = Field(default_factory=dict)

    model_config = ConfigDict(json_schema_extra={
        "private_paths": ["secret_hands"],
        "private_paths_by_audience": {
            "player": ["secret_hands.{audience.player_id}"],
            "llm": ["secret_hands.{audience.player_id}"],
        },
    })
```

Private values should not appear in non-terminal public, player, or LLM projections unless the audience is allowed to know them.

## Requests

`current_requests()` returns author-facing `RequestSpec` objects. The runtime turns them into managed `InteractionRequest` objects.

Every request needs a stable `key`. Include phase, actor, and turn information when needed:

```python
RequestSpec(
    key=f"choose_action:{player.id}:turn_{state.turn_number}",
    kind="choose_action",
    actor_id=player.id,
    mode="barrier",
    input_schema={
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["hold", "move"]}},
        "required": ["action"],
        "additionalProperties": False,
    },
    legal_options=LegalOptions(
        kind="choice",
        examples=[{"action": "hold"}],
    ),
)
```

Request modes:

- `single`: normal single request.
- `barrier`: many requests may remain pending until the kernel has enough final submissions.
- `timer`: deadline-oriented request. Include `deadline_at`.

## Legal Options

Legal options serve two jobs:

- guide frontends and LLMs toward valid actions
- provide examples that `validate_kernel()` and fake responders can submit

Use `LegalOptions.examples` whenever a request schema is not obvious. Standard helpers mark common affordances:

- `card_option(...)`
- `hint_option(...)`
- `approval_option(...)`
- `order_set_option(...)`

For complex payloads, include concrete examples even if options are present.

## Validation Issues

`validate_submission()` returns an empty list when a submission is legal. Return `ValidationIssue` objects for illegal moves:

```python
ValidationIssue(
    code="invalid_target",
    message="Move orders must target a known zone.",
    path=["payload", "orders", 0, "target"],
    hint="Choose one of the targets in legal_options.",
)
```

Use nested paths that point to the exact payload field. Good paths make generated-game repair much easier.

## Resolving Submissions

The runtime calls `resolve()` after accepted final submissions. For barrier games, return unchanged or partially updated state until enough final submissions are present.

Draft submissions are accepted and recorded with `submission.intent == "draft"`, but they do not trigger resolution and are not passed to `resolve()`. Final submissions use `submission.intent == "final"` and are passed to `resolve()`.

When a request is complete, include the request keys in `TransitionResult.resolved_request_keys`:

```python
return TransitionResult(
    new_state=new_state,
    events=[GameEventSpec(kind="batch_resolved", payload={"turn_number": state.turn_number})],
    resolved_request_keys=[request.spec_key for request in requests],
)
```

## Projections

`project_state()` returns only the visible state for the requested audience. The runtime wraps this in a full `Projection`.

Audience kinds:

- `public`
- `player`
- `llm`
- `moderator`
- `debug`

Keep truth state out of projections unless the audience is meant to see it. Terminal projections may reveal final outcomes.

## Runtime And Replay Tests

Use `validate_kernel()` first:

```python
issues = validate_kernel(MyKernel(), config=config, runs=3)
assert issues == []
```

Then use scripted replay:

```python
summary = await run_scripted_session(MyKernel(), config, script, seed=42)
replayed = await replay_session(
    MyKernel(),
    summary.config,
    summary.seed,
    summary.accepted_submissions,
    expected_trace=summary.comparable_trace,
)
assert replayed.matched is True
```

## LLM Players

LLM players use the same request pipeline as humans.

For deterministic tests, use `FakeLLMProvider` and `LLMResponder`:

```python
from llmgames.responders import FakeLLMProvider, LLMResponder

provider = FakeLLMProvider({"choose_action:alice:turn_1": {"action": "hold"}})
responder = LLMResponder(provider)
result = await responder.submit_for_request(session, session.requests[0])
assert result.accepted is True
assert result.submission.source == "llm"
```

For real model integration, use `HTTPJSONLLMProvider`. The provider endpoint must accept `{"context": PromptContext}` and return `{"payload": {...}, "metadata": {...}}`.

## Checklist For Generated Games

- Uses only public imports from `llmgames` and `llmgames.testing`.
- Defines a Pydantic state model.
- Uses stable `RequestSpec.key` values.
- Provides `input_schema` for every request.
- Provides legal options and examples for LLM guidance.
- Returns `ValidationIssue` with useful paths and hints.
- Does not mutate inputs in kernel methods.
- Projects only audience-visible data.
- Passes `validate_kernel()`.
- Includes at least one scripted replay test.
- Includes at least one LLM-player test when the game has autonomous players.
