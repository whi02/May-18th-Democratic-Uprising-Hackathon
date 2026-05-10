import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from backend.models.db import Session, get_db
from backend.schemas.schema import OkResponse, SessionCreate, SessionResponse
from backend.services.chain_service import remove_chain

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _build_profile_text(name: str, age: int, job: str) -> str:
    """플레이어 정보를 build_chain(profile=...)에 넘길 문자열로 조합."""
    return f"이름: {name}, 나이: {age}세, 직업: {job}"


@router.post("", response_model=dict[str, Any], status_code=201)
def create_session(body: SessionCreate, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    """새 세션 생성. 플레이어 프로필을 받아 DB에 저장하고 session_id를 반환한다."""
    session_id = str(uuid.uuid4())
    profile_text = _build_profile_text(body.player_name, body.player_age, body.player_job)

    session = Session(
        id=session_id,
        player_name=body.player_name,
        player_age=body.player_age,
        player_job=body.player_job,
        profile_text=profile_text,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {"status": "ok", "data": SessionResponse.model_validate(session)}


@router.get("/{session_id}", response_model=dict[str, Any])
def get_session(session_id: str, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    """세션 단건 조회."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    return {"status": "ok", "data": SessionResponse.model_validate(session)}


@router.delete("/{session_id}", response_model=dict[str, Any])
def delete_session(session_id: str, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    """세션 포기 처리. status를 'abandoned'로 변경하고 인메모리 chain을 제거한다."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    if session.status != "active":
        raise HTTPException(status_code=400, detail=f"이미 종료된 세션입니다. (status: {session.status})")

    session.status = "abandoned"
    db.commit()

    remove_chain(session_id)

    return {"status": "ok", "data": None}
