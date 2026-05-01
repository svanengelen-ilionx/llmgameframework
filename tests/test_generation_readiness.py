from pathlib import Path

import tomllib

import llmgames
from llmgames import GameConfig, Player
from llmgames.games import ComplexOrdersKernel, HanabiLiteKernel, SplitOrStealKernel, TicTacToeKernel
from llmgames.testing import validate_kernel


ROOT = Path(__file__).resolve().parents[1]


def test_package_readme_points_to_author_facing_readme() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["readme"] == "README.md"
    assert (ROOT / "README.md").exists()


def test_generation_readiness_docs_exist_and_cover_llm_players() -> None:
    required_files = [
        "README.md",
        "AUTHORING.md",
        "GENERATION_TEST.md",
        "docs/AGENT_GAME_AUTHORING.md",
        "docs/AGENT_PROMPT_TEMPLATE.md",
    ]
    for file_name in required_files:
        text = (ROOT / file_name).read_text(encoding="utf-8")
        assert "llmgames" in text

    generation_test = (ROOT / "GENERATION_TEST.md").read_text(encoding="utf-8")
    assert "LLMResponder" in generation_test
    assert "FakeLLMProvider" in generation_test
    assert "HTTPJSONLLMProvider" in generation_test


def test_agent_game_authoring_doc_is_self_contained_for_autonomous_agents() -> None:
    instructions = (ROOT / "docs" / "AGENT_GAME_AUTHORING.md").read_text(encoding="utf-8")
    required_phrases = [
        "autonomous AI coding agent",
        "Do not clone or inspect the framework repository",
        "Do not edit files inside the `llmgames` package",
        "python -m pip install llmgames",
        "llmgames @ git+https://github.com/svanengelen-ilionx/llmgameframework.git@main",
        "The distribution name is `llmgames`, and the import package is also `llmgames`.",
        "Public Imports",
        "Kernel Skeleton",
        "Player Experience Requirements",
        "validate_kernel()",
        "run_scripted_session()",
        "replay_session()",
        "FakeLLMProvider",
        "LLMResponder",
        "Audience.llm",
        "Done Criteria",
    ]

    for phrase in required_phrases:
        assert phrase in instructions


def test_agent_prompt_template_reinforces_user_experience_and_no_core_edits() -> None:
    prompt_template = (ROOT / "docs" / "AGENT_PROMPT_TEMPLATE.md").read_text(encoding="utf-8")

    assert "https://github.com/svanengelen-ilionx/llmgameframework/blob/main/docs/AGENT_GAME_AUTHORING.md" in prompt_template
    assert "Do not clone, inspect, or modify the llmgames framework repository" in prompt_template
    assert "at least one LLM player" in prompt_template
    assert "good end-user experience" in prompt_template
    assert "test commands and results" in prompt_template


def test_public_exports_include_generation_authoring_surface() -> None:
    expected_exports = {
        "Audience",
        "GameConfig",
        "GameEventSpec",
        "GameResult",
        "InteractionRequest",
        "LegalOption",
        "LegalOptions",
        "Message",
        "Player",
        "RequestSpec",
        "RulesContext",
        "RulesKernel",
        "StateProjection",
        "Submission",
        "SubmissionIntent",
        "TransitionResult",
        "ValidationIssue",
        "approval_option",
        "card_option",
        "hint_option",
        "order_set_option",
    }

    assert expected_exports.issubset(set(llmgames.__all__))


def test_reference_kernels_validate_for_generation_examples() -> None:
    two_player_config = GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])
    three_player_config = GameConfig(
        players=[
            Player(id="alice", name="Alice"),
            Player(id="bob", name="Bob"),
            Player(id="carol", name="Carol"),
        ]
    )
    cases = [
        (TicTacToeKernel(), two_player_config),
        (SplitOrStealKernel(), two_player_config),
        (HanabiLiteKernel(), two_player_config),
        (ComplexOrdersKernel(), three_player_config),
    ]

    for kernel, config in cases:
        assert validate_kernel(kernel, config=config, runs=3) == []


def test_internal_plan_no_longer_names_specific_order_game_as_core_target() -> None:
    plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")

    assert "Diplomacy-style" not in plan
    assert "historical implementation plan" in plan


def test_completed_historical_plans_were_removed() -> None:
    assert not (ROOT / "GENERATION_READINESS_PLAN.md").exists()
    assert not (ROOT / "PHASE5_CORE_GAPS.md").exists()


def test_package_install_path_is_documented_for_agents() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    instructions = (ROOT / "docs" / "AGENT_GAME_AUTHORING.md").read_text(encoding="utf-8")

    install_spec = "llmgames @ git+https://github.com/svanengelen-ilionx/llmgameframework.git@main"
    assert install_spec in readme
    assert install_spec in instructions
