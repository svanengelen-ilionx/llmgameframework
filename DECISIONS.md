# Implementation Decisions

Use `PENDING` for new decisions until the commit hash exists, then replace it with the commit hash that introduced the decision.

- fb08559: `Message` is a small projection-facing model with `kind`, optional `text`, `payload`, and `metadata`; runtime sequencing can be added later through events rather than message IDs.
- fb08559: `GameResult` is modeled as `status`, optional `winner_ids`, optional `reason`, and `metadata` so simple win/draw games work without encoding game-specific scoring.
- fb08559: `LegalOption` uses `value`, optional `label`, optional `payload`, and `metadata`; standard option kinds can generate examples from either `payload` or `value`.
- fb08559: Core Pydantic contract models use `extra="forbid"` to surface misspelled fields early in author code and diagnostics.
- 5281504: `GameSession.submit()` returns a `SubmitResult` for normal accept/reject outcomes; rejected submissions are recorded with `status="rejected"` instead of raising exceptions for expected lifecycle, schema, idempotency, or game-legality failures.
- 5281504: The in-memory runtime starts deterministic session IDs at `session_1` by default and deterministic per-session request/submission/event IDs at `req_1`, `sub_1`, and event sequence `1`.
- 5281504: Idempotent retry lookup happens before pending-status rejection for existing requests, so an exact retry can return the previous accepted submission after the original request has resolved; the same key with a changed payload is still rejected as an idempotency conflict.
- 0757ee4: Replay scripts target pending requests by `spec_key` when provided, falling back to actor-visible pending requests, so replay remains centered on author-stable request keys rather than historical runtime IDs.
- 0757ee4: Replay comparisons normalize runtime-generated timestamps out and compare request lifecycle, accepted submission payloads, final state, and final public/player projections.
- 0757ee4: Replay comparable submissions omit `source`; original runs may use `scripted`, `human`, or `llm`, while replay re-enters through `source="replay"` without changing game behavior.
- 46a8709: Public projections hide actor-specific pending requests; player/LLM audiences see their own requests, while public requests remain visible to public/moderator/debug audiences.
- 46a8709: Runtime resolution after an accepted submission passes all currently pending requests plus accepted submissions for those requests, allowing barrier kernels to resolve only after enough submissions are present.
- 46a8709: Phase 0B `assert_projection_private()` scans projection state and messages, not request affordances, because legal options may legitimately name allowable choices while unrevealed submitted choices must stay out of projected state/messages.
- 91cd7ec: Replay divergence reports the first nested comparable-trace path, using dotted object keys and bracketed list indices, while still avoiding a full deep-diff dependency in Phase 0.
