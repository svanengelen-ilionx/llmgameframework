# Phase Zero Ready Runtime Plan

## Executive Summary

This plan is the implementation-ready refinement of the verifiable interaction runtime design. It keeps the central architecture:

```text
RulesKernel + RequestSpec + Request/Submission Runtime + Projection + Validation + Replay
```

It incorporates the latest review feedback by tightening the author-facing API before coding starts:

- no generic `RulesKernel[StateT]` in the author surface
- `RequestSpec` is author-facing; `InteractionRequest` is runtime-managed
- every `RequestSpec` has an author-provided stable `key`
- legal options live on `RequestSpec` for Phase 0; no separate `legal_options()` method
- the kernel returns `StateProjection`, while the runtime builds full `Projection` envelopes
- `RulesContext` is defined narrowly and is not a dependency grab bag
- kernel methods are synchronous and pure; runtime/session methods are asynchronous
- invariants are split into harness-enforced vs documented contract rules
- privacy checks use metadata/path declarations, not intrusive `Secret(value)` wrappers
- Phase 0 scope is reduced: Tic-Tac-Toe is fully validated; Split or Steal must play through structurally

The core product remains a backend framework for games played by any mix of humans, LLMs, scripts, and assisted seats, with enough structured data for a web frontend to render state, legal interactions, submissions, events, progress, and reconnect flows.

## Core Development Loop

The framework is designed for LLM-authored game code. The primary loop is:

```text
generate kernel -> validate_kernel() -> replay failure -> read actionable diagnostics -> fix -> repeat
```

The first release should make this loop excellent before investing in storage, web routes, timers, or complex LLM orchestration.

## Design Principles

1. **Mechanical verifiability first.** Invalid game kernels should fail fast with structured, repairable diagnostics.
2. **Small author surface.** Game authors produce state models, request specs, validation, resolution, and state projections.
3. **Runtime owns runtime fields.** Session IDs, request IDs, statuses, event sequence numbers, correlation IDs, and event cursors are not authored by games.
4. **Sync rules, async runtime.** Rules are pure synchronous functions. Runtime methods are async from Phase 0 so LLM and web support do not force a redesign.
5. **Projection-first privacy.** Truth state is never served directly. The kernel supplies audience-filtered state payloads; runtime wraps them in projection envelopes.
6. **One request pipeline.** Humans, LLMs, scripts, timers, and replay all submit through the same request/submission path.
7. **Canonical examples are specification.** Reference games are few-shot examples for future generated games.
8. **Flat and greppable.** Avoid deep hierarchies and hidden registration mechanisms.

## Public API Promise

Game authors should import from `llmgames`, not internal modules.

```python
from llmgames import (
    Audience,
    GameConfig,
    GameResult,
    InteractionRequest,
    LegalOptions,
    Player,
    Projection,
    RequestMode,
    RequestSpec,
    RulesContext,
    RulesKernel,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)
```

Testing helpers should be stable through `llmgames.testing`:

```python
from llmgames.testing import (
    KernelIssue,
    ReplayResult,
    assert_projection_private,
    replay_session,
    run_scripted_session,
    validate_kernel,
)
```

Generated games should use only these public imports.

## Package Shape

Keep the implementation flat at first:

```text
llmgames/
    __init__.py       # public API re-exports
    models.py         # Pydantic contracts
    rules.py          # RulesKernel protocol and contract docs
    runtime.py        # async in-memory GameSession
    validation.py     # validate_kernel and diagnostics
    replay.py         # deterministic replay
    testing.py        # public test helpers
    responders.py     # scripted and later LLM responders
    llm.py            # async LLM provider and prompt context, later
    storage.py        # stores, later
    web.py            # FastAPI/SSE helpers, later
    games/
        tic_tac_toe.py
        split_or_steal.py
        hanabi_lite.py
```

## Sync/Async Boundary

This boundary is explicit from the start.

### Kernel Methods Are Sync

Rules kernel methods are synchronous, deterministic, and side-effect free. They do not await I/O because they do not perform I/O.

```python
state = kernel.initial_state(config, ctx)
specs = kernel.current_requests(state, ctx)
issues = kernel.validate_submission(state, request, submission, ctx)
transition = kernel.resolve(state, requests, submissions, ctx)
state_projection = kernel.project_state(state, audience, ctx)
```

### Runtime Methods Are Async

Session/runtime methods are asynchronous even in Phase 0.

```python
session = GameSession(kernel, config, seed=42)
await session.start()
projection = await session.projection(Audience.public())
await session.submit(request_id, payload, actor_id="alice", idempotency_key="...")
await session.advance()
```

This allows later LLM jobs, storage, SSE, and concurrent submissions to fit without changing the public session shape.

## Core Models

Use Pydantic v2 for all public contracts and reference-game truth states.

### Player

```python
class Player(BaseModel):
    id: str
    name: str
```

### GameConfig

```python
class GameConfig(BaseModel):
    players: list[Player]
    settings: dict[str, Any] = Field(default_factory=dict)
```

### Audience

Audience identifies who is viewing data.

```python
class Audience(BaseModel):
    kind: Literal["public", "player", "llm", "moderator", "debug"]
    player_id: str | None = None
```

LLM audience should default to the same visibility as the corresponding player.

### RulesContext

`RulesContext` must stay narrow.

```python
class RulesContext(BaseModel):
    players: list[Player]
    config: GameConfig
    current_event_seq: int = 0
```

It must not contain provider clients, stores, request registries, clocks, web objects, or arbitrary runtime services.

Randomness is deliberately excluded from general context in Phase 0. If later phases need random resolution after setup, add an explicit deterministic random source deliberately rather than sneaking it into a grab bag.

### RequestSpec

`RequestSpec` is what game authors return from `current_requests()`.

```python
class RequestSpec(BaseModel):
    key: str
    kind: str
    actor_id: str | None = None
    mode: RequestMode = "single"
    input_schema: dict[str, Any]
    legal_options: LegalOptions | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

The `key` is stable within the current pending interaction. It is not a runtime request ID.

Good keys:

```text
place_mark:alice
split_choice:bob:round_1
conversation_message:alice:turn_3
```

Bad keys:

```text
random UUID generated every call
list index only
timestamp
```

Phase 0 excludes deadlines from `RequestSpec`. Timer/deadline fields can be added when timer support is implemented.

### InteractionRequest

`InteractionRequest` is runtime-managed and derived from `RequestSpec`.

```python
class InteractionRequest(BaseModel):
    id: str
    session_id: str
    spec_key: str
    kind: str
    actor_id: str | None = None
    mode: RequestMode
    input_schema: dict[str, Any]
    legal_options: LegalOptions | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: RequestStatus
    correlation_id: str
    created_event_seq: int
    resolved_event_seq: int | None = None
```

Game authors never instantiate this directly.

### LegalOptions

Legal options are embedded in `RequestSpec` in Phase 0. There is no separate `legal_options()` kernel method.

Initial legal option kinds:

```text
choice
target_player
target_board_cell
text
structured_form
custom
```

`custom` must include examples so the validation harness can generate legal submissions.

```python
class LegalOptions(BaseModel):
    kind: str
    options: list[LegalOption] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Rule: if `kind == "custom"`, `examples` must contain at least one valid payload unless the request is system-only.

### Submission

```python
class Submission(BaseModel):
    id: str
    request_id: str
    actor_id: str | None
    source: Literal["human", "llm", "scripted", "timer", "system", "moderator", "replay"]
    payload: dict[str, Any]
    idempotency_key: str
    correlation_id: str
    submitted_at: datetime
    status: Literal["received", "accepted", "rejected", "superseded"] = "received"
```

### StateProjection

The kernel returns this, not a full runtime projection.

```python
class StateProjection(BaseModel):
    phase: str | None = None
    visible_state: dict[str, Any]
    visible_messages: list[Message] = Field(default_factory=list)
    result: GameResult | None = None
```

### Projection

The runtime builds this envelope.

```python
class Projection(BaseModel):
    session_id: str
    audience: Audience
    status: str
    phase: str | None = None
    visible_state: dict[str, Any]
    visible_requests: list[InteractionRequest]
    visible_messages: list[Message] = Field(default_factory=list)
    event_cursor: int
    result: GameResult | None = None
```

### TransitionResult

```python
class TransitionResult(BaseModel):
    new_state: BaseModel
    events: list[GameEventSpec] = Field(default_factory=list)
    resolved_request_keys: list[str] = Field(default_factory=list)
    rejected_submissions: list[ValidationIssue] = Field(default_factory=list)
```

The runtime maps resolved request keys to managed request IDs.

## RulesKernel Protocol

Avoid a generic author-facing protocol. Runtime validation and `state_model` enforce the important constraints.

```python
class RulesKernel(Protocol):
    game_id: str
    state_model: type[BaseModel]

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> BaseModel:
        ...

    def current_requests(self, state: BaseModel, ctx: RulesContext) -> list[RequestSpec]:
        ...

    def validate_submission(
        self,
        state: BaseModel,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        ...

    def resolve(
        self,
        state: BaseModel,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        ...

    def project_state(self, state: BaseModel, audience: Audience, ctx: RulesContext) -> StateProjection:
        ...
```

Game implementations should still annotate their concrete method arguments and returns with the concrete state type for readability and type checking.

Example:

```python
class TicTacToeKernel:
    game_id = "tic_tac_toe"
    state_model = TicTacToeState

    def current_requests(self, state: TicTacToeState, ctx: RulesContext) -> list[RequestSpec]:
        ...
```

## Request Matching

Request matching is settled before Phase 0 coding.

The runtime matches `RequestSpec`s to existing pending `InteractionRequest`s by `spec.key`.

Rules:

- `RequestSpec.key` must be unique among `current_requests()` for a state.
- If a pending request with the same key exists, the runtime keeps the existing managed request ID.
- If the same key appears with materially different `kind`, `actor_id`, `mode`, or schema while still pending, the runtime reports a request-spec conflict.
- If a previously pending key disappears from `current_requests()`, the runtime marks that managed request as cancelled/stale unless it was resolved in the same transition.
- A new key creates a new managed request.

This avoids positional matching and avoids forcing authors to manage runtime IDs.

## Enforced Versus Documented Invariants

### Harness-Enforced Invariants

The validation harness should check these in Phase 0 where practical:

- `initial_state()` returns an instance of `state_model`.
- `current_requests()` returns only `RequestSpec` objects.
- `current_requests()` is deterministic for the same state and context.
- `current_requests()` does not mutate state.
- request keys are unique among current requests.
- request keys are stable for unchanged pending interactions during replay.
- requests do not reference unknown actor IDs.
- `custom` legal options include examples.
- generated example submissions validate against request schemas.
- `validate_submission()` returns only `ValidationIssue` objects.
- `validate_submission()` does not mutate state, request, or submission.
- `resolve()` returns a `TransitionResult` with a valid `new_state`.
- `resolve()` does not mutate input state.
- `resolve()` resolves only request keys currently involved in resolution.
- `project_state()` returns a `StateProjection`.
- public/player projections do not leak values marked private by privacy metadata.
- replay with the same seed and submissions produces the same request/event sequence, excluding fields declared nondeterministic such as timestamps.

### Documented Contract Invariants

These are contract rules but are not reliably enforced by the Phase 0 harness:

- rules methods must not perform network calls
- rules methods must not perform file system or database I/O
- rules methods must not call LLM providers
- rules methods must not read wall-clock time directly
- rules methods should not depend on global mutable state
- rules methods should not use unseeded randomness

The framework can add optional stricter checks later, but Phase 0 diagnostics should not promise impossible enforcement.

## Privacy Metadata

Do not wrap truth-state values in `Secret(value)` for normal game logic. It pollutes author code.

Use privacy declarations instead.

Recommended Phase 0 shape:

```python
class SplitOrStealState(BaseModel):
    players: list[Player]
    choices: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "private_paths": ["choices"]
        }
    )
```

For tests, allow explicit forbidden values too:

```python
assert_projection_private(
    projection,
    forbidden_values=["steal", "split"],
    context="unrevealed Split or Steal choices",
)
```

The validation harness can start with simple path/value checks and become more sophisticated during Hanabi Lite.

## Validation Harness

Target API:

```python
issues = validate_kernel(TicTacToeKernel(), runs=100, seed=42)
assert not issues
```

Issue shape:

```python
class KernelIssue(BaseModel):
    severity: Literal["error", "warning"]
    method: str
    message: str
    hint: str | None = None
    seed: int | None = None
    replay: ReplaySpec | None = None
```

Validation strategy:

- instantiate initial state
- derive current request specs
- promote specs to managed requests
- generate submissions from legal options and examples
- validate and resolve submissions
- check mutation by comparing deep state copies
- build projections for public and player audiences
- check privacy metadata against projections
- replay submission history and compare request/event sequence
- stop with actionable issues when a method violates contract

## Diagnostics

Diagnostics are part of the API.

Examples:

```text
TicTacToeKernel.current_requests() returned duplicate RequestSpec.key='place_mark:alice'.
Expected: keys unique among current requests.
Hint: include enough state in the key to distinguish simultaneous requests.
```

```text
SplitOrStealKernel.resolve() mutated its input state.
Expected: resolve() returns a new state and leaves the input unchanged.
Hint: use state.model_copy(deep=True) before applying submitted choices.
```

```text
Custom LegalOptions for request key='choose_card:alice' has no examples.
Expected: custom legal options include at least one valid example payload for validation/replay.
Hint: add examples=[{"card_index": 0}] or use a standard legal option kind.
```

```text
SplitOrStealKernel.project_state(audience='public') leaked private path 'choices'.
Expected: public projection hides unrevealed choices.
Hint: expose only choice submission status until reveal.
```

## Deterministic Replay

Replay is Phase 0.

Target API:

```python
summary = await run_scripted_session(kernel, responders, seed=42)
replayed = await replay_session(kernel, summary.config, summary.seed, summary.submissions)
assert replayed.comparable_events == summary.comparable_events
```

Replay comparison should ignore declared nondeterministic runtime fields such as timestamps. It should compare:

- request spec keys
- managed request lifecycle sequence
- accepted submissions
- game event kinds and payloads
- final state
- final projections for public/player audiences

Replay failure should report the first divergence and include the replay seed and submissions.

## Runtime Core

The Phase 0 runtime is async but in-memory.

Responsibilities:

- create a session from kernel, config, and seed
- hold truth state
- build narrow `RulesContext`
- ask kernel for `RequestSpec`s
- promote specs to `InteractionRequest`s by key
- keep managed request IDs stable while keys remain pending
- accept submissions against request IDs
- enforce request lifecycle and idempotency
- call kernel validation and resolution methods
- assign event sequence numbers
- build full `Projection` envelopes from `StateProjection` plus runtime data
- record submissions for replay

The runtime must not assume:

- fixed turn order
- one active request
- one player acts at a time
- all requests are human-facing

## Canonical Reference Games

Reference games should be complete, self-contained, consistent, and deliberately boring.

### Tic-Tac-Toe

Phase 0 requires full validation.

Must demonstrate:

- one active request at a time
- stable request key
- `target_board_cell` legal options
- immutable `resolve()` pattern
- public projection
- deterministic replay

### Split Or Steal

Phase 0 requires structural play-through. Full hidden-choice projection validation can land in Phase 1.

Must demonstrate in Phase 0:

- simultaneous choice requests
- request keys per actor/phase
- barrier resolution after both submissions
- play to terminal result through submissions

Must demonstrate by Phase 1:

- unrevealed choices hidden from public projection
- validation harness catches hidden-choice leakage
- first simple LLM responder path

### Hanabi Lite

Phase 2 reference game.

Must demonstrate:

- private truth state with card identities
- privacy metadata/path checks
- player-specific projections
- legal hint options
- LLM prompt privacy checks

### Diplomacy-Style Orders Spike

Later spike, not a complete game.

Must demonstrate:

- large simultaneous order sets
- draft/final submission behavior
- deadline/timer support
- batch resolution diagnostics

## Revised Phases

### Phase 0: Verifiable Kernel And Replay MVP

Goal: prove the authoring/validation loop with a simple game and a structural simultaneous game.

Deliverables:

- stable public API in `llmgames.__init__`
- Pydantic core models
- non-generic `RulesKernel` protocol
- `RulesContext` definition
- `RequestSpec.key`
- `RequestSpec` / `InteractionRequest` split
- legal options embedded on `RequestSpec`
- `StateProjection` / runtime `Projection` split
- async in-memory `GameSession`
- request matching by key
- idempotent submission acceptance
- basic event sequencing
- `validate_kernel()` skeleton and core checks
- deterministic replay helpers
- Tic-Tac-Toe fully validated
- Split or Steal structural play-through
- actionable diagnostic fixtures

Exit criteria:

- Tic-Tac-Toe passes `validate_kernel()`.
- Tic-Tac-Toe replays identically from seed and submissions.
- Split or Steal plays to completion through simultaneous request/submission flow.
- Invalid fixture kernels produce actionable diagnostics.
- No runtime code assumes fixed turn order or a single pending request.

### Phase 1: Simultaneous Privacy And LLM Responder MVP

Goal: harden simultaneous hidden submissions and prove LLMs use the same pipeline.

Deliverables:

- Split or Steal hidden-choice projection validation
- privacy metadata checks for simple paths
- fake async LLM provider
- prompt context builder from projection + request legal options
- structured LLM submission model
- correlated `llm.*` events
- retry/failure diagnostics

Exit criteria:

- Split or Steal passes validation including hidden-choice leakage checks.
- LLM output becomes a normal submission.
- Invalid LLM output produces actionable diagnostics.
- Prompt context does not use truth state directly.

### Phase 2: Hidden Information Pressure Test

Goal: validate projection safety with a real hidden-information game.

Deliverables:

- Hanabi Lite reference game
- richer privacy path checks
- card/hint legal option primitives
- LLM prompt privacy tests
- property-based tests for hidden-information invariants

Exit criteria:

- Hanabi Lite passes validation.
- Public/player/LLM projections match expected visibility.
- Projection leak diagnostics are understandable.

### Phase 3: Storage, Reconnect, And Web Adapter

Goal: expose the already-validated runtime to browser frontends.

Deliverables:

- store protocols
- JSON or SQLite local store
- snapshot serialization
- FastAPI router helpers
- projection endpoint
- request/submission endpoints
- SSE stream with audience filtering
- reconnect tests

Exit criteria:

- browser refresh recovers visible projection and pending requests
- SSE resumes from event cursor
- stored sessions replay or reload consistently

### Phase 4: Timers, Deadlines, Assisted Seats

Goal: add richer runtime behavior after the core loop is proven.

Deliverables:

- fake-clock service
- timer request mode
- deadline expiration
- seat capabilities
- LLM suggestion + human approval flow
- approval legal option primitive

Exit criteria:

- timers are deterministic under test
- human-with-LLM-assist can approve/edit/reject suggestions
- timeout behavior is visible as correlated events

### Phase 5: Complex Orders Spike

Goal: pressure-test large simultaneous order surfaces and batch resolution.

Deliverables:

- Diplomacy-style orders spike
- order-set legal option primitive
- draft/final submissions
- batch resolution event structure
- replay tests for batch resolution

Exit criteria:

- many actors can submit and revise order sets
- final submissions resolve as one barrier
- diagnostics remain useful under complex interactions

## First Sprint Checklist

Build only:

- `Player`, `GameConfig`, `Audience`
- `RequestSpec` with `key`
- `InteractionRequest`
- `LegalOptions` with `custom.examples`
- `Submission`
- `StateProjection` and `Projection`
- `TransitionResult`
- `RulesContext`
- non-generic `RulesKernel`
- async in-memory `GameSession`
- request matching by key
- basic `validate_kernel()`
- basic replay
- Tic-Tac-Toe kernel
- tests for complete Tic-Tac-Toe play and replay

Do not build yet:

- OpenRouter
- FastAPI
- storage backends
- timers/deadlines
- assisted seats
- Hanabi
- full Split or Steal validation
- broad legal option vocabulary

## Open Questions After This Refinement

- Should `RequestSpec.key` be namespaced by game phase automatically or entirely author-owned?
- How strict should runtime conflict detection be when a pending key reappears with different legal options?
- Should `TransitionResult.resolved_request_keys` be optional if the runtime can infer resolved requests from submitted request IDs?
- What is the minimal privacy path syntax that handles Hanabi without becoming a query language?
- Should validation require every standard legal option kind to include examples too, or can examples be generated from options?
- Which comparable event fields should replay include by default?
- How should generated examples balance comments for LLM guidance against readability?

## Success Criteria

The design is ready for broader implementation when:

- a simple generated kernel can be validated and repaired without reading runtime internals
- request matching by key survives replay and simultaneous requests
- projections cleanly separate kernel-visible data from runtime metadata
- validation errors name the broken kernel method and repair path
- LLM and human submissions use the same request pipeline
- web/storage work can be implemented as adapters over the verified core
