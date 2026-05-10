import sys
from pathlib import Path
from typing import Any, Literal, Optional

# chain.py, config.py, utils.py 등이 프로젝트 루트에 위치 (feat/ai-module 리팩토링)
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from chain import build_chain  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI
from prompt import (  # noqa: E402
    DEATH_EPILOGUE_PROMPT,
    SURVIVAL_EPILOGUE_PROMPT,
)
from utils import EndingDetector  # noqa: E402

# session_id(UUID str) → RunnableWithMessageHistory 인메모리 캐시
_chain_store: dict[str, Any] = {}

# 테일 전용 엔딩 감지 — 유저 입력에 마커 포함 시 오탐 방지
_ending_detector = EndingDetector(config.ENDING_MARKERS, config.ENDING_TAIL_BUFFER)

# 위험도 키워드 → delta 매핑 (음수: 위험, 양수: 안전)
_DANGER_MAP: list[tuple[int, list[str]]] = [
    (-25, ["발포", "총격", "총탄", "총에", "총을 맞", "쓰러졌", "숨졌", "사망"]),
    (-15, ["체포", "구타", "폭행", "진압", "부상", "끌려", "피투성"]),
    (-5,  ["시위", "저항", "격렬", "충돌", "맞섰", "대치"]),
    (+10, ["숨었", "피신", "탈출", "도망", "안전한", "몸을 피"]),
]


def compute_danger_delta(answer: str) -> int:
    """AI 응답에서 위험 키워드를 분석해 생존 확률 변화량을 반환한다."""
    delta = 0
    for d, keywords in _DANGER_MAP:
        if any(kw in answer for kw in keywords):
            delta += d
    return max(-30, min(10, delta))


def get_or_create_chain(session_id: str, profile_text: str) -> Any:
    """캐시에 chain이 없으면 build_chain()으로 생성 후 저장, 있으면 반환.

    서버 재시작 시 캐시가 비워지므로 profile_text(DB 저장값)를 받아 재생성한다.
    """
    if session_id not in _chain_store:
        _chain_store[session_id] = build_chain(profile=profile_text)
    return _chain_store[session_id]


EndingType = Optional[Literal["사망", "생존"]]


def invoke_chain(
    session_id: str,
    profile_text: str,
    user_message: str,
    game_date: int = 18,
    location: str = "",
    character: str = "",
) -> tuple[str, EndingType, int, int]:
    """chain을 실행하고 (응답 텍스트, 엔딩 종류, 다음 날짜) 튜플을 반환한다.

    <<사망>> 또는 <<생존>> 마커가 응답에 포함되면 해당 엔딩 종류를 반환한다.
    날짜는 AI 응답의 '📅 1980년 5월 OO일' 패턴을 파싱해 추출한다.
    """
    import re as _re

    chain = get_or_create_chain(session_id, profile_text)

    # 컨텍스트 헤더만 붙이고 메시지는 순수 텍스트로 전달
    # JSON 전체를 input으로 보내면 condense 단계가 항상 같은 쿼리를 생성해 반복 응답 발생
    context_parts = []
    if location:
        context_parts.append(location)
    if character:
        context_parts.append(f"{character} 중심")
    context_parts.append(f"5월 {game_date}일")
    header = " · ".join(context_parts)
    char_note = f"이 장면의 주요 등장인물은 {character}이다. {character}의 시각과 대사를 중심으로 장면을 구성해라.\n" if character else ""
    payload = f"[{header}]\n{char_note}{user_message}"

    result = chain.invoke(
        {"input": payload},
        config={"configurable": {"session_id": session_id}},
    )
    answer: str = result["answer"]

    # AI 응답 첫 줄에서 날짜 추출 (예: 📅 1980년 5월 21일)
    next_date = game_date
    date_match = _re.search(r"📅\s*1980년\s*5월\s*(\d+)일", answer)
    if date_match:
        parsed = int(date_match.group(1))
        if 18 <= parsed <= 27:
            next_date = parsed

    ending: EndingType = None
    detected = _ending_detector.detect(answer)
    if detected == "death":
        ending = "사망"
        answer = answer.replace(config.ENDING_MARKERS["death"], "").rstrip()
    elif detected == "survival":
        ending = "생존"
        answer = answer.replace(config.ENDING_MARKERS["survival"], "").rstrip()

    danger_delta = compute_danger_delta(answer)
    return answer, ending, next_date, danger_delta


def generate_epilogue(ending: str) -> str:
    """엔딩 종류에 따라 에필로그 텍스트를 생성해 반환한다."""
    _EPILOGUE_MAP = {
        "사망": DEATH_EPILOGUE_PROMPT,
        "생존": SURVIVAL_EPILOGUE_PROMPT,
    }
    prompt = _EPILOGUE_MAP.get(ending, SURVIVAL_EPILOGUE_PROMPT)
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")
    response = llm.invoke(prompt)
    return str(response.content)


def remove_chain(session_id: str) -> None:
    """세션 종료(abandoned/dead/survived) 시 캐시에서 chain 제거."""
    _chain_store.pop(session_id, None)
