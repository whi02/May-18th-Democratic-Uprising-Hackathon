# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

5.18 민주화운동 해커톤 프로젝트. 플레이어가 1980년 5월 광주를 배경으로 역사적 사건을 체험하는 인터랙티브 내러티브 챗봇 "제타(Zeta)". LangChain + Gemini API + FAISS RAG로 구현한다.

## Commands

```bash
# 의존성 설치
uv syncA

# 벡터스토어 최초 생성 (518_data_v3.pdf 필요, rate limit으로 시간 소요)
uv run python ingest.py

# 실행
uv run python main.py
```

환경변수: `.env` 파일에 `GOOGLE_API_KEY` 설정 필요.

## Architecture

```
ingest.py    # PDF → 청킹 → Gemini 임베딩 → FAISS 저장 (최초 1회)
retriever.py # 저장된 FAISS 로드 → Retriever 반환
prompt.py    # ZETA_SYSTEM, CONDENSE_SYSTEM, 에필로그 프롬프트 정의
chain.py     # history-aware retriever + stuff chain → RunnableWithMessageHistory
main.py      # 플레이어 프로필 수집 → 대화 루프 → 엔딩 판정 → 에필로그
```

### 핵심 설계

- **LLM**: `gemini-2.5-flash-lite` (`chain.py`의 `build_chain(model=...)` 파라미터로 교체 가능)
- **임베딩**: `models/gemini-embedding-001`. `retriever.py`의 `GeminiEmbeddings`는 `embed_query`를 `embed_documents`로 우회하는 서브클래스 — Gemini API 호환성 때문.
- **RAG 흐름**: `create_history_aware_retriever` (대화 기록 기반 질문 재구성) → `_clean_docs` (노이즈 제거) → `create_stuff_documents_chain` → `create_retrieval_chain`
- **세션 메모리**: `InMemoryChatMessageHistory`를 `_sessions` dict에 session_id로 관리
- **엔딩 시스템**: LLM 응답에 `<<사망>>` / `<<생존>>` 마커가 포함되면 `main.py`가 감지해 에필로그를 출력하고 종료
- **ingest.py 재시작 안전**: 중간에 중단돼도 기존 벡터스토어 이어서 처리 (배치마다 저장)

### 프롬프트 구조 (`prompt.py`)

- `ZETA_SYSTEM`: 나레이터 역할, 플레이어 프로필 주입(`{profile}`), 날짜 표기 형식, 선택지 금지, 죽음/생존 마커 규칙, 역사 자료(`{context}`) 활용 원칙
- `CONDENSE_SYSTEM`: 대화 기록을 독립 질문으로 재구성 (히스토리 인식 retriever용)
- `DEATH_EPILOGUE_PROMPT` / `SURVIVAL_EPILOGUE_PROMPT`: 엔딩 후 에필로그 지시문

## 역할 분담

- `ai-module/` (chain.py, retriever.py 등) — 민기 담당, 수정 금지
- `backend/` — whi02 (나) 담당 (FastAPI 서버)
- `frontend/` — whi02 담당 (나) (웹 UI)

## Backend

기술 스택: FastAPI / Python 3.11 / MySQL 8.0

```bash
# 백엔드 실행
uvicorn main:app --reload
```

AI 모듈 연동: chain.py의 build_chain() import해서 사용

## 코딩 규칙

- type hint 필수
- .env 하드코딩 금지 (GOOGLE_API_KEY, DB_URL 등)
- API 응답 형식: {"status": "ok", "data": ...} 통일
- 주석 한국어로 작성
- ai-module/ 폴더 절대 수정 금지