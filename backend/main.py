from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from backend.models.db import create_tables, engine
from backend.routers import chat, session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """서버 시작 시 테이블 생성 및 스키마 마이그레이션."""
    create_tables()
    # 기존 DB에 game_date 컬럼이 없을 경우 추가 (신규 DB는 create_tables에서 처리됨)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN game_date INTEGER NOT NULL DEFAULT 18"))
            conn.commit()
        except Exception:
            pass  # 이미 있으면 무시
    yield


app = FastAPI(
    title="5.18 민주화운동 내러티브 챗봇 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session.router)
app.include_router(chat.router)
