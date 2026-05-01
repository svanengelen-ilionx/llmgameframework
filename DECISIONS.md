# Implementation Decisions

- 2026-05-01: `Message` is a small projection-facing model with `kind`, optional `text`, `payload`, and `metadata`; runtime sequencing can be added later through events rather than message IDs.
- 2026-05-01: `GameResult` is modeled as `status`, optional `winner_ids`, optional `reason`, and `metadata` so simple win/draw games work without encoding game-specific scoring.
- 2026-05-01: `LegalOption` uses `value`, optional `label`, optional `payload`, and `metadata`; standard option kinds can generate examples from either `payload` or `value`.
- 2026-05-01: Core Pydantic contract models use `extra="forbid"` to surface misspelled fields early in author code and diagnostics.
