import tempfile
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from llmgames import (
    ActionContext,
    ActionResult,
    BaseGameModule,
    Engine,
    Event,
    GameInfo,
    GameResult,
    GameView,
    JsonlRecorder,
    Observation,
    Player,
    RunConfig,
    ViewRequest,
    action,
    empty_schema,
    read_jsonl_trace,
)
from llmgames.core.controllers import ScriptedController, intent
from llmgames.core.engine import InvalidIntentError


@dataclass
class TraceState:
    players: list[Player]
    done: bool = False


class TraceGame(BaseGameModule):
    def get_info(self) -> GameInfo:
        return GameInfo(name="Trace Game", min_players=1, max_players=1)

    def create_initial_state(self, players: Sequence[Player], seed: int | None = None) -> TraceState:
        return TraceState(players=list(players))

    def get_observation(self, state: TraceState, player_id: str) -> Observation:
        return Observation(player_id=player_id, rules="Finish once.")

    def get_view(self, state: TraceState, request: ViewRequest) -> GameView:
        return GameView(name=request.name, visibility="public", data={"done": state.done})

    def get_result(self, state: TraceState) -> GameResult:
        return GameResult(is_terminal=self.is_terminal(state), reason="done" if state.done else "running")

    def is_terminal(self, state: TraceState) -> bool:
        return state.done

    @action(description="Finish.", input_schema=empty_schema())
    def finish(
        self,
        state: TraceState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        state.done = True
        return ActionResult(success=True, events=[Event("finished", "Finished", {"player_id": player_id})])


class TracingTests(unittest.TestCase):
    def test_engine_emits_ordered_trace_events_and_views(self) -> None:
        player = Player("p1", "Player 1")

        summary = Engine(
            TraceGame(),
            RunConfig(players=[player], controllers={"p1": ScriptedController([intent("finish")])}),
        ).run()

        trace_types = [event.type for event in summary.trace_events]
        self.assertEqual(summary.trace_events[0].seq, 1)
        self.assertEqual([event.seq for event in summary.trace_events], list(range(1, len(summary.trace_events) + 1)))
        self.assertIn("run_started", trace_types)
        self.assertIn("turn_started", trace_types)
        self.assertIn("player_turn_started", trace_types)
        self.assertIn("available_actions_created", trace_types)
        self.assertIn("intent_received", trace_types)
        self.assertIn("domain_event", trace_types)
        self.assertIn("action_applied", trace_types)
        self.assertIn("view_emitted", trace_types)
        self.assertEqual(trace_types[-1], "run_finished")

        domain_events = [event for event in summary.trace_events if event.type == "domain_event"]
        self.assertEqual(domain_events[0].payload["event"].type, "finished")

        views = [event for event in summary.trace_events if event.type == "view_emitted"]
        self.assertEqual(views[-1].payload["view"].data["done"], True)

    def test_jsonl_recorder_writes_trace_events(self) -> None:
        player = Player("p1", "Player 1")
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "trace.jsonl"
            Engine(
                TraceGame(),
                RunConfig(
                    players=[player],
                    controllers={"p1": ScriptedController([intent("finish")])},
                    recorder=JsonlRecorder(trace_path),
                ),
            ).run()

            payloads = read_jsonl_trace(trace_path)

        self.assertEqual(payloads[0]["type"], "run_started")
        self.assertEqual(payloads[-1]["type"], "run_finished")
        self.assertTrue(all("seq" in payload for payload in payloads))

    def test_run_failed_is_traced_before_reraising(self) -> None:
        player = Player("p1", "Player 1")
        engine = Engine(
            TraceGame(),
            RunConfig(players=[player], controllers={"p1": ScriptedController([intent("unknown")])}),
        )

        with self.assertRaises(InvalidIntentError):
            engine.run()

        self.assertEqual(engine.trace_recorder.events[-1].type, "run_failed")
        self.assertEqual(engine.trace_recorder.events[-1].payload["error_type"], "InvalidIntentError")


if __name__ == "__main__":
    unittest.main()
