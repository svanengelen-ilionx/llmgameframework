# Implementation Decisions

- 2026-05-01: `Message` is a small projection-facing model with `kind`, optional `text`, `payload`, and `metadata`; runtime sequencing can be added later through events rather than message IDs.
- 2026-05-01: `GameResult` is modeled as `status`, optional `winner_ids`, optional `reason`, and `metadata` so simple win/draw games work without encoding game-specific scoring.
- 2026-05-01: `LegalOption` uses `value`, optional `label`, optional `payload`, and `metadata`; standard option kinds can generate examples from either `payload` or `value`.
- 2026-05-01: Core Pydantic contract models use `extra="forbid"` to surface misspelled fields early in author code and diagnostics.
- 2026-05-01: `GameSession.submit()` returns a `SubmitResult` for normal accept/reject outcomes; rejected submissions are recorded with `status="rejected"` instead of raising exceptions for expected lifecycle, schema, idempotency, or game-legality failures.
- 2026-05-01: The in-memory runtime starts deterministic session IDs at `session_1` by default and deterministic per-session request/submission/event IDs at `req_1`, `sub_1`, and event sequence `1`.
- 2026-05-01: Idempotent retry lookup happens before pending-status rejection for existing requests, so an exact retry can return the previous accepted submission after the original request has resolved; the same key with a changed payload is still rejected as an idempotency conflict.
