from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema
from pydantic import BaseModel

from llmgames.models import (
    Audience,
    GameConfig,
    InteractionRequest,
    LegalOptions,
    Player,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)
from llmgames.rules import RulesKernel


class KernelIssue(BaseModel):
    severity: Literal["error", "warning"] = "error"
    method: str
    message: str
    hint: str | None = None
    seed: int | None = None


def validate_kernel(
    kernel: RulesKernel,
    *,
    runs: int = 1,
    seed: int = 0,
    config: GameConfig | None = None,
    max_steps: int = 9,
) -> list[KernelIssue]:
    issues: list[KernelIssue] = []
    config = config or _default_config()
    ctx = RulesContext(config=config)

    state = _call_initial_state(kernel, config, ctx, issues)
    if state is None:
        return issues

    _validate_projection(kernel, state, ctx, issues)

    request_sequence = 0
    submission_sequence = 0
    for step in range(max(1, min(runs, max_steps))):
        requests = _call_current_requests(kernel, state, ctx, issues)
        if requests is None:
            return issues
        if not requests:
            break

        if _has_error(issues):
            return issues

        promoted_requests: list[InteractionRequest] = []
        accepted_submissions: list[Submission] = []
        for spec in requests:
            request_sequence += 1
            request = _promote_request(spec, session_id="validation", sequence=request_sequence)
            promoted_requests.append(request)
            payload = _validated_example_payload(spec, request, issues, seed)
            if payload is None:
                return issues if _has_error(issues) else issues

            submission_sequence += 1
            submission = Submission(
                id=f"validation_sub_{submission_sequence}",
                request_id=request.id,
                actor_id=request.actor_id,
                source="scripted",
                payload=payload,
                idempotency_key=f"validation_{submission_sequence}",
                correlation_id=request.correlation_id,
                submitted_at=datetime.now(timezone.utc),
            )
            validation_errors = _call_validate_submission(
                kernel, state, request, submission, ctx, issues
            )
            if validation_errors is None or _has_error(issues):
                return issues
            if any(issue.severity == "error" for issue in validation_errors):
                issues.append(
                    KernelIssue(
                        method="validate_submission",
                        message=f"Generated legal example for RequestSpec.key='{request.spec_key}' was rejected by validate_submission().",
                        hint="Make legal_options examples describe actually legal submissions for the current state.",
                        seed=seed,
                    )
                )
                return issues
            accepted_submissions.append(submission)

        if not accepted_submissions:
            return issues

        transition = _call_resolve(kernel, state, promoted_requests, accepted_submissions, ctx, issues)
        if transition is None:
            return issues
        state = transition.new_state
        _validate_projection(kernel, state, ctx, issues)
        if _has_error(issues):
            return issues

    return issues


def _default_config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])


def _call_initial_state(
    kernel: RulesKernel, config: GameConfig, ctx: RulesContext, issues: list[KernelIssue]
) -> BaseModel | None:
    try:
        state = kernel.initial_state(config, ctx)
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        issues.append(_exception_issue("initial_state", exc))
        return None
    if not isinstance(state, kernel.state_model):
        issues.append(
            KernelIssue(
                method="initial_state",
                message=f"initial_state() returned {type(state).__name__}, expected {kernel.state_model.__name__}.",
                hint="Return an instance of the kernel's state_model.",
            )
        )
        return None
    return state


def _call_current_requests(
    kernel: RulesKernel,
    state: BaseModel,
    ctx: RulesContext,
    issues: list[KernelIssue],
) -> list[RequestSpec] | None:
    before = _dump(state)
    try:
        first = kernel.current_requests(state, ctx)
        second = kernel.current_requests(state, ctx)
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        issues.append(_exception_issue("current_requests", exc))
        return None

    if _dump(state) != before:
        issues.append(
            KernelIssue(
                method="current_requests",
                message="current_requests() mutated its input state.",
                hint="Return request specs without changing the state object.",
            )
        )
        return None
    if not isinstance(first, list) or any(not isinstance(item, RequestSpec) for item in first):
        issues.append(
            KernelIssue(
                method="current_requests",
                message="current_requests() must return list[RequestSpec].",
                hint="Construct RequestSpec objects for active interactions.",
            )
        )
        return None
    if _dump(first) != _dump(second):
        issues.append(
            KernelIssue(
                method="current_requests",
                message="current_requests() returned different specs for the same state and context.",
                hint="Use stable RequestSpec.key values and avoid randomness or counters in current_requests().",
            )
        )
        return None

    keys = [spec.key for spec in first]
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        issues.append(
            KernelIssue(
                method="current_requests",
                message=f"current_requests() returned duplicate RequestSpec.key={duplicate_keys[0]!r}.",
                hint="Include enough state in the key to distinguish simultaneous requests.",
            )
        )
    player_ids = {player.id for player in ctx.config.players}
    for spec in first:
        if spec.actor_id is not None and spec.actor_id not in player_ids:
            issues.append(
                KernelIssue(
                    method="current_requests",
                    message=f"RequestSpec.key='{spec.key}' references unknown actor_id='{spec.actor_id}'.",
                    hint="Use an id from ctx.config.players or leave actor_id unset for public/system requests.",
                )
            )
        if spec.legal_options and spec.legal_options.kind == "custom" and not spec.legal_options.examples:
            issues.append(
                KernelIssue(
                    method="current_requests",
                    message=f"Custom LegalOptions for request key='{spec.key}' has no examples.",
                    hint="Add examples with at least one payload that passes input_schema and validate_submission().",
                )
            )
    return first


def _validated_example_payload(
    spec: RequestSpec,
    request: InteractionRequest,
    issues: list[KernelIssue],
    seed: int,
) -> dict[str, Any] | None:
    payload = _example_payload(spec.legal_options)
    if payload is None:
        issues.append(
            KernelIssue(
                severity="warning",
                method="current_requests",
                message=f"RequestSpec.key='{spec.key}' has no legal-options example the validator can submit.",
                hint="Add legal_options examples or use a standard option kind with concrete options.",
                seed=seed,
            )
        )
        return None
    try:
        validate_json_schema(instance=payload, schema=request.input_schema)
    except JsonSchemaValidationError as exc:
        issues.append(
            KernelIssue(
                method="current_requests",
                message=f"Generated example for RequestSpec.key='{spec.key}' does not match input_schema: {exc.message}.",
                hint="Align legal_options examples with input_schema.",
                seed=seed,
            )
        )
        return None
    return payload


def _call_validate_submission(
    kernel: RulesKernel,
    state: BaseModel,
    request: InteractionRequest,
    submission: Submission,
    ctx: RulesContext,
    issues: list[KernelIssue],
) -> list[ValidationIssue] | None:
    before_state = _dump(state)
    before_request = _dump(request)
    before_submission = _dump(submission)
    try:
        result = kernel.validate_submission(state, request, submission, ctx)
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        issues.append(_exception_issue("validate_submission", exc))
        return None
    if _dump(state) != before_state or _dump(request) != before_request or _dump(submission) != before_submission:
        issues.append(
            KernelIssue(
                method="validate_submission",
                message="validate_submission() mutated state, request, or submission.",
                hint="Return ValidationIssue objects without changing inputs.",
            )
        )
        return None
    if not isinstance(result, list) or any(not isinstance(item, ValidationIssue) for item in result):
        issues.append(
            KernelIssue(
                method="validate_submission",
                message="validate_submission() must return list[ValidationIssue].",
                hint="Return an empty list for accepted submissions.",
            )
        )
        return None
    return result


def _call_resolve(
    kernel: RulesKernel,
    state: BaseModel,
    requests: list[InteractionRequest],
    submissions: list[Submission],
    ctx: RulesContext,
    issues: list[KernelIssue],
) -> TransitionResult | None:
    before = _dump(state)
    try:
        transition = kernel.resolve(state, requests, submissions, ctx)
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        issues.append(_exception_issue("resolve", exc))
        return None
    if _dump(state) != before:
        issues.append(
            KernelIssue(
                method="resolve",
                message="resolve() mutated its input state.",
                hint="Use state.model_copy(deep=True) before applying accepted submissions.",
            )
        )
        return None
    if not isinstance(transition, TransitionResult):
        issues.append(
            KernelIssue(
                method="resolve",
                message="resolve() must return TransitionResult.",
                hint="Wrap the new state and events in TransitionResult.",
            )
        )
        return None
    if not isinstance(transition.new_state, kernel.state_model):
        issues.append(
            KernelIssue(
                method="resolve",
                message=f"resolve() returned new_state={type(transition.new_state).__name__}, expected {kernel.state_model.__name__}.",
                hint="TransitionResult.new_state must remain the kernel's state_model.",
            )
        )
        return None
    involved_keys = {request.spec_key for request in requests}
    invalid_resolved = [key for key in transition.resolved_request_keys if key not in involved_keys]
    if invalid_resolved:
        issues.append(
            KernelIssue(
                method="resolve",
                message=f"resolve() resolved request key '{invalid_resolved[0]}' that was not involved in this resolution.",
                hint="Only include keys from the requests passed to resolve().",
            )
        )
    return transition


def _validate_projection(
    kernel: RulesKernel, state: BaseModel, ctx: RulesContext, issues: list[KernelIssue]
) -> None:
    audiences = [
        Audience.public(),
        *(Audience.player(player.id) for player in ctx.config.players),
        *(Audience.llm(player.id) for player in ctx.config.players),
    ]
    for audience in audiences:
        before = _dump(state)
        try:
            projection = kernel.project_state(state, audience, ctx)
        except Exception as exc:  # pragma: no cover - defensive diagnostic path
            issues.append(_exception_issue("project_state", exc))
            return
        if _dump(state) != before:
            issues.append(
                KernelIssue(
                    method="project_state",
                    message="project_state() mutated its input state.",
                    hint="Build visible_state separately from truth state.",
                )
            )
            return
        if not isinstance(projection, StateProjection):
            issues.append(
                KernelIssue(
                    method="project_state",
                    message="project_state() must return StateProjection.",
                    hint="Return kernel-visible state only; the runtime builds Projection envelopes.",
                )
            )
            return
        _validate_private_paths(state, projection, audience, issues)


def _validate_private_paths(
    state: BaseModel,
    projection: StateProjection,
    audience: Audience,
    issues: list[KernelIssue],
) -> None:
    if projection.result is not None or audience.kind not in {"public", "player", "llm"}:
        return
    state_data = state.model_dump(mode="json")
    private_paths = _private_paths(state, audience)
    for private_path in private_paths:
        for private_value in _values_at_path(state_data, private_path):
            if _is_empty_private_value(private_value):
                continue
            visible_path = _find_value_path(projection.visible_state, private_value, path="visible_state")
            if visible_path is not None:
                issues.append(
                    KernelIssue(
                        method="project_state",
                        message=(
                            f"project_state(audience='{_audience_key(audience)}') leaked private path "
                            f"'{private_path}' at projection path '{visible_path}'."
                        ),
                        hint="Hide declared private values from non-terminal public/player/LLM projections.",
                    )
                )
                return


def _private_paths(state: BaseModel, audience: Audience) -> list[str]:
    extra = getattr(state, "model_config", {}).get("json_schema_extra") or {}
    paths = list(extra.get("private_paths", []))
    by_audience = extra.get("private_paths_by_audience", {})
    if isinstance(by_audience, dict):
        paths.extend(by_audience.get(audience.kind, []))
    return [_format_private_path(path, audience) for path in paths]


def _format_private_path(path: str, audience: Audience) -> str:
    return path.replace("{audience.player_id}", audience.player_id or "")


def _values_at_path(data: Any, path: str) -> list[Any]:
    values = [data]
    for part in path.split("."):
        next_values: list[Any] = []
        for value in values:
            if part == "*":
                if isinstance(value, dict):
                    next_values.extend(value.values())
                elif isinstance(value, list):
                    next_values.extend(value)
                continue
            if isinstance(value, dict) and part in value:
                next_values.append(value[part])
            elif isinstance(value, list) and part.isdigit():
                index = int(part)
                if 0 <= index < len(value):
                    next_values.append(value[index])
        values = next_values
        if not values:
            break
    return values


def _is_empty_private_value(value: Any) -> bool:
    return value is None or value == {} or value == []


def _find_value_path(container: Any, value: Any, *, path: str) -> str | None:
    if container == value:
        return path
    if isinstance(container, dict):
        for key, item in container.items():
            found = _find_value_path(item, value, path=f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(container, list):
        for index, item in enumerate(container):
            found = _find_value_path(item, value, path=f"{path}[{index}]")
            if found is not None:
                return found
        return None
    return None


def _audience_key(audience: Audience) -> str:
    if audience.player_id is None:
        return audience.kind
    return f"{audience.kind}:{audience.player_id}"


def _promote_request(spec: RequestSpec, *, session_id: str, sequence: int) -> InteractionRequest:
    return InteractionRequest(
        id=f"req_{sequence}",
        session_id=session_id,
        spec_key=spec.key,
        kind=spec.kind,
        actor_id=spec.actor_id,
        mode=spec.mode,
        input_schema=spec.input_schema,
        legal_options=spec.legal_options,
        metadata=spec.metadata,
        status="pending",
        correlation_id=f"corr_{sequence}",
        created_event_seq=sequence - 1,
    )


def _example_payload(legal_options: LegalOptions | None) -> dict[str, Any] | None:
    if legal_options is None:
        return None
    if legal_options.examples:
        return legal_options.examples[0]
    if legal_options.options:
        option = legal_options.options[0]
        if option.payload is not None:
            return option.payload
        if isinstance(option.value, dict):
            return option.value
        return {"value": option.value}
    return None


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _has_error(issues: list[KernelIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def _exception_issue(method: str, exc: Exception) -> KernelIssue:
    return KernelIssue(
        method=method,
        message=f"{method}() raised {type(exc).__name__}: {exc}",
        hint="Keep kernel methods synchronous, deterministic, and side-effect free.",
    )
