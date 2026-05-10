from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from backend.models.db import Message, Session, get_db
from backend.schemas.schema import (
    ChatRequest,
    ChatResponse,
    MessageResponse,
    SessionResponse,
)
from backend.services.chain_service import (
    generate_epilogue,
    invoke_chain,
    remove_chain,
)

router = APIRouter(prefix="/sessions", tags=["chat"])

# ending 마커 → sessions.status 매핑
_ENDING_STATUS: dict[str, str] = {
    "사망": "dead",
    "생존": "survived",
}


@router.post("/{session_id}/chat", response_model=dict[str, Any])
def chat(
    session_id: str,
    body: ChatRequest,
    db: DBSession = Depends(get_db),
) -> dict[str, Any]:
    """플레이어 메시지를 받아 AI 응답을 반환한다.

    ending 감지 시 세션 status 업데이트, chain 캐시 제거, 에필로그 생성을 수행한다.
    """
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if session.status != "active":
        raise HTTPException(status_code=400, detail=f"이미 종료된 세션입니다. (status: {session.status})")

    # 유저 메시지 저장
    user_msg = Message(
        session_id=session_id,
        role="user",
        content=body.message,
        has_ending_marker=False,
    )
    db.add(user_msg)
    db.flush()  # id 확보 (commit 전)

    # AI chain 호출
    try:
        answer, ending, next_date, danger_delta = invoke_chain(
            session_id,
            session.profile_text,
            body.message,
            game_date=session.game_date,
            location=body.location or "",
            character=body.character or "",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {e}")

    # 날짜 업데이트
    session.game_date = next_date

    has_marker = ending is not None

    # 어시스턴트 메시지 저장
    assistant_msg = Message(
        session_id=session_id,
        role="assistant",
        content=answer,
        has_ending_marker=has_marker,
    )
    db.add(assistant_msg)

    # ending 감지 시 세션 status 업데이트
    epilogue: str | None = None
    if ending is not None:
        session.status = _ENDING_STATUS[ending]
        epilogue = generate_epilogue(ending)
        remove_chain(session_id)

    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    data = ChatResponse(
        user_message=MessageResponse.model_validate(user_msg),
        assistant_message=MessageResponse.model_validate(assistant_msg),
        session_status=session.status,
        ending=ending,
        epilogue=epilogue,
        game_date=session.game_date,
        danger_delta=danger_delta,
    )
    return {"status": "ok", "data": data}


@router.get("/{session_id}/messages", response_model=dict[str, Any])
def get_messages(
    session_id: str,
    db: DBSession = Depends(get_db),
) -> dict[str, Any]:
    """세션의 전체 대화 기록을 오름차순으로 반환한다. 프론트 히스토리 복원용."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    data = [MessageResponse.model_validate(m) for m in messages]
    return {"status": "ok", "data": data}
