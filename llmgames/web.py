from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from llmgames.models import Audience, GameConfig, GameEventSpec
from llmgames.rules import RulesKernel
from llmgames.runtime import GameSession
from llmgames.storage import SessionStore, restore_session, snapshot_session


class CreateSessionRequest(BaseModel):
    config: GameConfig
    seed: int = 0
    session_id: str = "session_1"


class SubmitRequest(BaseModel):
    payload: dict[str, Any]
    actor_id: str | None = None
    idempotency_key: str
    source: str = "human"


def create_game_router(kernel: RulesKernel, store: SessionStore) -> APIRouter:
    router = APIRouter()

    @router.post("/sessions")
    async def create_session(request: CreateSessionRequest):
        existing = await store.load(request.session_id)
        if existing is not None:
            raise HTTPException(status_code=409, detail="Session already exists.")
        session = GameSession(kernel, request.config, seed=request.seed, session_id=request.session_id)
        await session.start()
        await store.save(snapshot_session(session))
        return {"session_id": session.session_id, "status": session.status}

    @router.get("/sessions/{session_id}/projection")
    async def get_projection(
        session_id: str,
        audience_kind: str = Query("public"),
        player_id: str | None = None,
    ):
        session = await _load_session(kernel, store, session_id)
        return (await session.projection(_audience(audience_kind, player_id))).model_dump(mode="json")

    @router.post("/sessions/{session_id}/requests/{request_id}/submissions")
    async def submit(session_id: str, request_id: str, request: SubmitRequest):
        session = await _load_session(kernel, store, session_id)
        result = await session.submit(
            request_id,
            request.payload,
            actor_id=request.actor_id,
            idempotency_key=request.idempotency_key,
            source=request.source,
        )
        await store.save(snapshot_session(session))
        return result.model_dump(mode="json")

    @router.get("/sessions/{session_id}/events")
    async def stream_events(
        session_id: str,
        cursor: int = 0,
        audience_kind: str = Query("public"),
        player_id: str | None = None,
    ):
        session = await _load_session(kernel, store, session_id)
        audience = _audience(audience_kind, player_id)
        return EventSourceResponse(_event_stream(session.events, cursor=cursor, audience=audience))

    return router


def create_game_app(kernel: RulesKernel, store: SessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(create_game_router(kernel, store))
    return app


async def _load_session(kernel: RulesKernel, store: SessionStore, session_id: str) -> GameSession:
    snapshot = await store.load(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return restore_session(kernel, snapshot)


def _audience(kind: str, player_id: str | None) -> Audience:
    if kind == "public":
        return Audience.public()
    if kind == "player":
        if player_id is None:
            raise HTTPException(status_code=400, detail="player_id is required for player audience.")
        return Audience.player(player_id)
    if kind == "llm":
        if player_id is None:
            raise HTTPException(status_code=400, detail="player_id is required for llm audience.")
        return Audience.llm(player_id)
    if kind == "moderator":
        return Audience.moderator()
    if kind == "debug":
        return Audience.debug()
    raise HTTPException(status_code=400, detail="Unknown audience kind.")


async def _event_stream(events: list[GameEventSpec], *, cursor: int, audience: Audience):
    for sequence, event in enumerate(events, start=1):
        if sequence <= cursor or not _event_visible(event, audience):
            continue
        yield {
            "id": str(sequence),
            "event": event.kind,
            "data": json.dumps(event.model_dump(mode="json"), sort_keys=True),
        }


def _event_visible(event: GameEventSpec, audience: Audience) -> bool:
    if audience.kind == "debug":
        return True
    if event.visibility == "debug":
        return False
    if event.visibility == "player":
        return audience.kind in {"player", "llm", "moderator"}
    return True