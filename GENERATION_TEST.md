# Medium-Complexity LLM Generation Test

This document describes how to test whether an LLM can generate a medium-complexity game using `llmgames` as an imported Python package.

## Test Inputs To Give The LLM

Give the LLM these files as context:

- `docs/AGENT_GAME_AUTHORING.md`
- `docs/AGENT_PROMPT_TEMPLATE.md`
- `README.md`
- `AUTHORING.md`
- `GENERATION_TEST.md`
- `llmgames/games/tic_tac_toe.py`
- `llmgames/games/split_or_steal.py`
- `llmgames/games/hanabi_lite.py`
- `llmgames/games/complex_orders.py`
- `tests/test_complex_orders.py`
- `tests/test_responders.py`

Do not give the LLM permission to edit `llmgames` core files during the test.

For autonomous coding agents, prefer giving [docs/AGENT_GAME_AUTHORING.md](docs/AGENT_GAME_AUTHORING.md) as the single canonical instruction link and [docs/AGENT_PROMPT_TEMPLATE.md](docs/AGENT_PROMPT_TEMPLATE.md) as the user prompt wrapper.

## Generation Prompt

Use this prompt shape:

```text
Generate a medium-complexity game using the llmgames package.

Requirements:
- Create one Python module for the game kernel and state model.
- Create one pytest file for validation, replay, invalid submissions, projection privacy if relevant, and LLM-player behavior.
- Use only public imports from llmgames and llmgames.testing in the game and tests, except llmgames.responders may be used for LLM-player tests.
- Do not modify llmgames core package files.
- The game must have at least three players.
- The game must use simultaneous barrier requests.
- The game must include at least one medium-complexity nested payload, such as an order set, bid set, vote plan, or allocation plan.
- The game must include draft/final submissions or explain why final-only is appropriate.
- The game must include legal_options with examples that match input_schema.
- The game must return useful ValidationIssue paths and hints for invalid submissions.
- The game must emit at least one structured GameEventSpec on resolution.
- The game must include at least one LLM player test using FakeLLMProvider and LLMResponder.

After generating code, ensure validate_kernel() returns no errors and the pytest file passes.
```

## Local Test Setup

From the repository root:

```bash
python -m pip install -e '.[test]'
python -m pytest
```

Create generated files outside the package core, for example:

```text
generated_games/medium_game.py
tests/test_generated_medium_game.py
```

## Required Generated Tests

The generated pytest file should include these checks.

### 1. Kernel Validation

```python
def test_generated_kernel_validates() -> None:
    issues = validate_kernel(GeneratedKernel(), config=_config(), runs=3)
    assert issues == []
```

### 2. Scripted Replay

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

### 3. Invalid Submission Diagnostics

```python
@pytest.mark.asyncio
async def test_generated_game_reports_nested_invalid_payload() -> None:
    session = GameSession(GeneratedKernel(), _config())
    await session.start()
    result = await session.submit(
        "req_1",
        {"orders": [{"bad": True}]},
        actor_id="alice",
        idempotency_key="bad-order",
    )
    assert result.accepted is False
    assert result.issues[0].path
    assert result.issues[0].hint is not None
```

### 4. LLM Player Test

Use a fake provider for deterministic behavior:

```python
@pytest.mark.asyncio
async def test_generated_game_accepts_llm_player_submission() -> None:
    session = GameSession(GeneratedKernel(), _config())
    await session.start()
    provider = FakeLLMProvider({
        session.requests[0].spec_key: _legal_payload_for(session.requests[0]),
    })
    responder = LLMResponder(provider)

    result = await responder.submit_for_request(session, session.requests[0])

    assert result.accepted is True
    assert result.submission.source == "llm"
```

### 5. LLM Privacy Test

If the game has hidden information, build prompt context from `Audience.llm(player_id)` and assert hidden truth-state values are absent from `context.visible_state` and `context.visible_messages`.

## Optional Real LLM Player Test

For a real LLM provider, use `HTTPJSONLLMProvider`:

```python
from llmgames.llm import HTTPJSONLLMProvider
from llmgames.responders import LLMResponder

provider = HTTPJSONLLMProvider(
    "https://your-provider.example/complete",
    headers={"Authorization": "Bearer ..."},
)
responder = LLMResponder(provider)
```

The provider endpoint receives:

```json
{"context": {"request_id": "...", "visible_state": {}, "input_schema": {}, "legal_options": {}}}
```

It must return:

```json
{"payload": {"your": "submission"}, "metadata": {"model": "provider-name"}}
```

Do not run real-provider tests by default in CI. Gate them behind an environment variable.

## Pass Criteria

The generated game passes the test if:

- it imports without touching core package files
- it uses only public authoring imports
- `validate_kernel()` returns no errors
- scripted replay matches
- invalid submissions produce actionable `ValidationIssue` paths and hints
- LLM-player submissions enter through `LLMResponder` and `GameSession.submit(source="llm")`
- hidden information, if present, is not visible to unauthorized LLM audiences
- the repository test suite still passes
