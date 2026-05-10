import os
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Enum,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DB_URL", "sqlite:///./518db.sqlite")

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    player_name = Column(String(50), nullable=False)
    player_age = Column(Integer, nullable=False)
    player_job = Column(String(100), nullable=False)
    profile_text = Column(Text, nullable=False)
    status = Column(
        Enum("active", "dead", "survived", "abandoned"),
        nullable=False,
        default="active",
    )
    # 현재 게임 내 날짜 (5월 18일 = 18 시작, 최대 27)
    game_date = Column(Integer, nullable=False, default=18)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    # 'user' | 'assistant'
    role = Column(Enum("user", "assistant"), nullable=False)
    content = Column(Text, nullable=False)
    # <<사망>>/<<생존>> 마커 포함 여부 (TINYINT(1))
    has_ending_marker = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    session = relationship("Session", back_populates="messages")


def get_db():
    """FastAPI 의존성 주입용 DB 세션 생성기."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """테이블이 없을 경우 생성 (개발/테스트용)."""
    Base.metadata.create_all(bind=engine)
