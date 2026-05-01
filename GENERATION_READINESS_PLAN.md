# Generation Readiness Plan

Goal: make the project ready for a test where an LLM generates a medium-complexity game by importing `llmgames`, then runs that game with scripted, human-like, and LLM players.

## Desired State

- The package has a concise README for installation and orientation.
- The LLM receives an authoring guide instead of the internal implementation plan.
- The generation prompt forbids core edits and internal imports.
- The generated game can use medium-complexity features: barrier requests, hidden information, draft/final submissions, order sets, timers, and LLM players.
- The generated game ships with tests using `validate_kernel()`, scripted replay, invalid-submission diagnostics, projection privacy checks, and `LLMResponder`.

## Implementation Steps

1. Add `README.md` as the package readme and point `pyproject.toml` at it.
2. Add `AUTHORING.md` with the public authoring contract and examples.
3. Add `GENERATION_TEST.md` with exact instructions for running the LLM generation test, including LLM-player checks.
4. Clean stale internal wording that would confuse generated-game authors.
5. Add a small readiness regression test that verifies docs and public exports stay aligned.
6. Run the full test suite and import/validator smoke checks.

## Success Criteria

- A generation LLM can be given `README.md`, `AUTHORING.md`, `GENERATION_TEST.md`, and selected reference game files as context.
- The generated game uses only public imports.
- The generated game validates, runs, replays, and supports at least one LLM player.
- The package test suite remains green.
