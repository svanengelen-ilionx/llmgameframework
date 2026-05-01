# Resolved Phase 5 Core Gap Report

This historical report records the core gap found while building the complex-orders spike and how it was resolved. It is not current authoring guidance; use [AUTHORING.md](AUTHORING.md), [GENERATION_TEST.md](GENERATION_TEST.md), and [docs/AGENT_GAME_AUTHORING.md](docs/AGENT_GAME_AUTHORING.md) for current game-generation instructions.

The Phase 5 constraint was that the spike must not add game-specific concepts to the core package. If a reference game exposed missing core support, the issue had to be documented before any core runtime or contract change was made.

## Gap 1: Draft/final revisions are not first-class runtime semantics

### What the spike needs

Complex simultaneous-order games often let each actor submit an order set, revise it before a deadline, and then mark the order set final. The batch should resolve only when the final submissions required for the barrier are present.

### Original support gap

`GameSession.submit()` accepts a submission and immediately calls the kernel resolution path. The runtime supports exact idempotent retries, but it does not provide a way for a later accepted submission to supersede an earlier accepted draft for the same request.

### Why this was a core gap

A game kernel can encode draft/final inside payloads, but the runtime still records each accepted submission as equally effective. The kernel then has to reconstruct latest-submission semantics from the full accepted submission history. That is possible for a narrow game, but it is not a clear, reusable contract for generated games.

### Smallest general-purpose core change candidate

Introduce a general submission phase or superseding policy that is independent of any specific game. Candidate shapes:

- `Submission.intent: "draft" | "final"` plus runtime rules for when final submissions participate in barrier resolution.
- `RequestSpec.metadata["submission_policy"]` with a documented `latest_per_actor` or `draft_final` policy.
- A separate helper that kernels can call to derive latest accepted submissions without changing stored submission models.

### Core-unchanged alternative considered

Keep Phase 5's first reference game final-only: each actor submits one complete order set and the existing barrier resolves them as one batch. This validates large order payloads, order-set diagnostics, batch events, and replay without claiming draft/final revision support.

### Original recommendation

Implement the final-only complex-orders spike first. Defer runtime draft/final semantics until the reference game and tests make the required general contract clearer.

### Implemented resolution

Approved for implementation. Draft/final support is implemented as a general `Submission.intent` field. Draft submissions are accepted and recorded without resolving requests; final submissions retain the existing validation and resolution path. Resolution considers accepted final submissions only, so reference games can permit draft revisions without game-specific runtime behavior.