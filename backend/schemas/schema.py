from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Session ──────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    """POST /sessions 요청 바디."""
    player_name: str = Field(..., max_length=50)
    player_age: int = Field(..., ge=1, le=120)
    player_job: str = Field(..., max_length=100)


class SessionResponse(BaseModel):
    """세션 단건 응답."""
    id: str
    player_name: str
    player_age: int
    player_job: str
    profile_text: str
    status: Literal["active", "dead", "survived", "abandoned"]
    game_date: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Message ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """POST /sessions/{session_id}/chat 요청 바디."""
    message: str = Field(..., min_length=1)
    # 프론트에서 날짜 override 필요 시 사용, 없으면 DB 값 사용
    game_date: Optional[int] = Field(None, ge=18, le=27)
    location: Optional[str] = Field(None, max_length=100)   # 취재 장소
    character: Optional[str] = Field(None, max_length=50)   # 취재 인물


class MessageResponse(BaseModel):
    """메시지 단건 응답."""
    id: int
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    has_ending_marker: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    """POST /sessions/{session_id}/chat 응답."""
    user_message: MessageResponse
    assistant_message: MessageResponse
    # 엔딩 발생 시 변경된 세션 status 반환
    session_status: Literal["active", "dead", "survived", "abandoned"]
    # 엔딩 마커 감지 시 엔딩 종류, 없으면 null
    ending: Optional[Literal["사망", "생존"]] = None
    # 엔딩 발생 시 에필로그 본문, 없으면 null
    epilogue: Optional[str] = None
    # 응답 후 현재 날짜 (AI가 날짜 진행시켰을 수 있음)
    game_date: int
    # 생존 확률 변화량 (음수: 위험, 양수: 안전, 0: 중립)
    danger_delta: int = 0


# ── 공통 래퍼 ─────────────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    """상태만 반환하는 단순 응답 (DELETE 등)."""
    status: Literal["ok"] = "ok"
