# llmgames

`llmgames` is a Python package for building verifiable game runtimes where humans, LLMs, scripts, timers, and assisted seats all use the same request and submission pipeline.

The package is designed for generated game code. A game author implements a small synchronous `RulesKernel`; the async runtime owns request IDs, submissions, replay, projections, events, storage, web adapters, deadlines, and LLM responders.

## Install For Development

```bash
python -m pip install -e '.[test]'
python -m pytest
```

## Authoring Loop

Generated games should follow this loop:

```text
generate kernel -> validate_kernel() -> run scripted session -> replay -> fix diagnostics -> repeat
```

Use public imports from `llmgames` and `llmgames.testing`:

```python
from pydantic import BaseModel, Field

from llmgames import (
    Audience,
    GameConfig,
    GameEventSpec,
    GameResult,
    InteractionRequest,
    LegalOption,
    LegalOptions,
    Player,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)
from llmgames.testing import replay_session, run_scripted_session, validate_kernel
```

## Minimal Kernel Shape

```python
class MyState(BaseModel):
    phase: str = "playing"


class MyKernel:
    game_id = "my_game"
    state_model = MyState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> MyState:
        return MyState()

    def current_requests(self, state: MyState, ctx: RulesContext) -> list[RequestSpec]:
        return []

    def validate_submission(
        self,
        state: MyState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        return []

    def resolve(
        self,
        state: MyState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        return TransitionResult(new_state=state)

    def project_state(self, state: MyState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(visible_state=state.model_dump(mode="json"))
```

See [AUTHORING.md](AUTHORING.md) for the complete authoring contract and [GENERATION_TEST.md](GENERATION_TEST.md) for the medium-complexity LLM generation test, including LLM players.

If you want to hand an autonomous AI coding agent one GitHub link and ask it to create a game without editing this framework, use [docs/AGENT_GAME_AUTHORING.md](docs/AGENT_GAME_AUTHORING.md). A copy-paste user prompt is available in [docs/AGENT_PROMPT_TEMPLATE.md](docs/AGENT_PROMPT_TEMPLATE.md).

## Reference Games

Reference kernels live in `llmgames.games`:

- `TicTacToeKernel`: simple alternating turns.
- `SplitOrStealKernel`: simultaneous barrier submissions.
- `HanabiLiteKernel`: hidden information and card/hint legal options.
- `ComplexOrdersKernel`: order-set legal options, draft/final submissions, and batch resolution.

## Validation

```python
from llmgames import GameConfig, Player
from llmgames.games import ComplexOrdersKernel
from llmgames.testing import validate_kernel

config = GameConfig(players=[
    Player(id="alice", name="Alice"),
    Player(id="bob", name="Bob"),
    Player(id="carol", name="Carol"),
])

issues = validate_kernel(ComplexOrdersKernel(), config=config, runs=3)
assert issues == []
```
