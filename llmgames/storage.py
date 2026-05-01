from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from llmgames.models import GameConfig, GameEventSpec, InteractionRequest, Submission
from llmgames.rules import RulesKernel
from llmgames.runtime import GameSession


class SessionSnapshot(BaseModel):
    session_id: str
    game_id: str
    seed: int
    status: str
    event_seq: int
    request_seq: int
    submission_seq: int
    config: GameConfig
    state: dict
    requests: list[InteractionRequest] = Field(default_factory=list)
    submissions: list[Submission] = Field(default_factory=list)
    events: list[GameEventSpec] = Field(default_factory=list)


class SessionStore(Protocol):
    async def save(self, snapshot: SessionSnapshot) -> None:
        ...

    async def load(self, session_id: str) -> SessionSnapshot | None:
        ...

    async def delete(self, session_id: str) -> None:
        ...

    async def list_session_ids(self) -> list[str]:
        ...


class JSONFileSessionStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    async def save(self, snapshot: SessionSnapshot) -> None:
        await asyncio.to_thread(self._save_sync, snapshot)

    async def load(self, session_id: str) -> SessionSnapshot | None:
        return await asyncio.to_thread(self._load_sync, session_id)

    async def delete(self, session_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, session_id)

    async def list_session_ids(self) -> list[str]:
        return await asyncio.to_thread(self._list_session_ids_sync)

    def _save_sync(self, snapshot: SessionSnapshot) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(snapshot.session_id)
        path.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _load_sync(self, session_id: str) -> SessionSnapshot | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        return SessionSnapshot.model_validate_json(path.read_text(encoding="utf-8"))

    def _delete_sync(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()

    def _list_session_ids_sync(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json"))

    def _path(self, session_id: str) -> Path:
        if "/" in session_id or "\\" in session_id:
            raise ValueError("session_id must not contain path separators")
        return self.directory / f"{session_id}.json"


def snapshot_session(session: GameSession) -> SessionSnapshot:
    if session.state is None:
        raise RuntimeError("Cannot snapshot a session before it has started.")
    return SessionSnapshot(
        session_id=session.session_id,
        game_id=session.kernel.game_id,
        seed=session.seed,
        status=session.status,
        event_seq=session.event_seq,
        request_seq=session._request_seq,
        submission_seq=session._submission_seq,
        config=session.config,
        state=session.state.model_dump(mode="json"),
        requests=session.requests,
        submissions=session.submissions,
        events=session.events,
    )


def restore_session(kernel: RulesKernel, snapshot: SessionSnapshot) -> GameSession:
    if kernel.game_id != snapshot.game_id:
        raise ValueError(
            f"Snapshot game_id={snapshot.game_id!r} cannot be restored with kernel game_id={kernel.game_id!r}."
        )
    session = GameSession(kernel, snapshot.config, seed=snapshot.seed, session_id=snapshot.session_id)
    session.state = kernel.state_model.model_validate(snapshot.state)
    session.status = snapshot.status
    session.event_seq = snapshot.event_seq
    session._request_seq = snapshot.request_seq
    session._submission_seq = snapshot.submission_seq
    session._requests = [request.model_copy(deep=True) for request in snapshot.requests]
    session._submissions = [submission.model_copy(deep=True) for submission in snapshot.submissions]
    session._events = [event.model_copy(deep=True) for event in snapshot.events]
    session._accepted_by_idempotency = {
        (submission.request_id, submission.idempotency_key): submission
        for submission in session._submissions
        if submission.status == "accepted"
    }
    return session