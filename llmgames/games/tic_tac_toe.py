from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from llmgames import (
    Audience,
    GameConfig,
    GameEventSpec,
    GameResult,
    InteractionRequest,
    LegalOption,
    LegalOptions,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)

Mark = Literal["X", "O"]


class TicTacToeState(BaseModel):
    board: list[list[str | None]] = Field(
        default_factory=lambda: [[None, None, None], [None, None, None], [None, None, None]]
    )
    current_player_index: int = 0
    winner_id: str | None = None
    draw: bool = False


class TicTacToeKernel:
    game_id = "tic_tac_toe"
    state_model = TicTacToeState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> TicTacToeState:
        return TicTacToeState()

    def current_requests(self, state: TicTacToeState, ctx: RulesContext) -> list[RequestSpec]:
        if state.winner_id is not None or state.draw:
            return []
        player = ctx.config.players[state.current_player_index]
        return [
            RequestSpec(
                key=f"place_mark:{player.id}",
                kind="place_mark",
                actor_id=player.id,
                input_schema={
                    "type": "object",
                    "properties": {
                        "row": {"type": "integer", "minimum": 0, "maximum": 2},
                        "col": {"type": "integer", "minimum": 0, "maximum": 2},
                    },
                    "required": ["row", "col"],
                    "additionalProperties": False,
                },
                legal_options=LegalOptions(
                    kind="target_board_cell",
                    options=[
                        LegalOption(value=f"{row},{col}", payload={"row": row, "col": col})
                        for row in range(3)
                        for col in range(3)
                        if state.board[row][col] is None
                    ],
                ),
            )
        ]

    def validate_submission(
        self,
        state: TicTacToeState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        if request.actor_id is not None and submission.actor_id != request.actor_id:
            return [
                ValidationIssue(
                    code="wrong_actor",
                    message="Only the requested player may place this mark.",
                    path=["actor_id"],
                )
            ]
        row = submission.payload.get("row")
        col = submission.payload.get("col")
        if not isinstance(row, int) or not isinstance(col, int) or not (0 <= row <= 2 and 0 <= col <= 2):
            return [
                ValidationIssue(
                    code="invalid_cell",
                    message="Move must target a board cell with row and col between 0 and 2.",
                    path=["payload"],
                )
            ]
        if state.board[row][col] is not None:
            return [
                ValidationIssue(
                    code="occupied_cell",
                    message="That board cell is already occupied.",
                    path=["payload", "row"],
                    hint="Choose an empty cell from legal_options.",
                )
            ]
        return []

    def resolve(
        self,
        state: TicTacToeState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        if not requests or not submissions:
            return TransitionResult(new_state=state)

        request = requests[-1]
        submission = submissions[-1]
        new_state = state.model_copy(deep=True)
        player = next(player for player in ctx.config.players if player.id == request.actor_id)
        mark: Mark = "X" if ctx.config.players.index(player) == 0 else "O"
        row = submission.payload["row"]
        col = submission.payload["col"]
        new_state.board[row][col] = mark

        winner_mark = _winner_mark(new_state.board)
        if winner_mark is not None:
            new_state.winner_id = ctx.config.players[0 if winner_mark == "X" else 1].id
        elif all(cell is not None for board_row in new_state.board for cell in board_row):
            new_state.draw = True
        else:
            new_state.current_player_index = (new_state.current_player_index + 1) % len(ctx.config.players)

        return TransitionResult(
            new_state=new_state,
            events=[
                GameEventSpec(
                    kind="mark_placed",
                    payload={"player_id": player.id, "row": row, "col": col, "mark": mark},
                )
            ],
            resolved_request_keys=[request.spec_key],
        )

    def project_state(
        self, state: TicTacToeState, audience: Audience, ctx: RulesContext
    ) -> StateProjection:
        result = None
        if state.winner_id is not None:
            result = GameResult(status="win", winner_ids=[state.winner_id], reason="three_in_a_row")
        elif state.draw:
            result = GameResult(status="draw", reason="board_full")
        return StateProjection(
            phase="complete" if result else "playing",
            visible_state={
                "board": state.board,
                "current_player_id": None
                if result
                else ctx.config.players[state.current_player_index].id,
            },
            result=result,
        )


def _winner_mark(board: list[list[str | None]]) -> str | None:
    lines = [
        *board,
        [board[0][0], board[1][0], board[2][0]],
        [board[0][1], board[1][1], board[2][1]],
        [board[0][2], board[1][2], board[2][2]],
        [board[0][0], board[1][1], board[2][2]],
        [board[0][2], board[1][1], board[2][0]],
    ]
    for line in lines:
        if line[0] is not None and line[0] == line[1] == line[2]:
            return line[0]
    return None
