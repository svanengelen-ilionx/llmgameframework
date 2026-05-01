from llmgames.games import SplitOrStealKernel, TicTacToeKernel
from llmgames.testing import validate_kernel


def test_tic_tac_toe_passes_kernel_validation() -> None:
    issues = validate_kernel(TicTacToeKernel(), runs=5, seed=42)

    assert issues == []


def test_split_or_steal_passes_kernel_validation() -> None:
    issues = validate_kernel(SplitOrStealKernel(), runs=3, seed=42)

    assert issues == []
