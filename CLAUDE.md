# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

5.18 민주화운동 해커톤 프로젝트. "제타(Zeta)" 스타일의 AI 어시스턴트를 LangChain으로 구현한다. 담당 범위는 AI 모델 레이어(체인 구성, 프롬프트, RAG 등)이며, 데이터 소스로 `518_data_v3.pdf`를 활용한다.

## Commands

```bash
# 의존성 설치
uv sync

# 패키지 추가
uv add langchain langchain-community langchain-openai faiss-cpu pypdf

# 실행
uv run python main.py
```

## Architecture

```
main.py              # 진입점, 대화 루프, 엔딩 처리
chain.py             # RAG 체인 조립 (history-aware retriever + stuff QA)
retriever.py         # FAISS 벡터스토어 로더 (Gemini Embeddings)
prompt.py            # NARRATIVE_SYSTEM_PROMPT + condense/epilogue 프롬프트
ingest.py            # PDF → 청크 → 임베딩 → FAISS 인덱스 빌드
utils.py             # StreamingBuffer / EndingDetector / sanitize_prompt_field
config.py            # 모델·경로·청크·재시도·마커 등 모든 설정 단일 출처
```

### 핵심 설계 방향

- **RAG 구조**: `518_data_v3.pdf`를 청킹·임베딩하여 FAISS 벡터스토어에 저장 → history-aware retriever + stuff documents chain으로 질의응답
- **제타 페르소나**: `prompt.py`의 `NARRATIVE_SYSTEM_PROMPT`에서 캐릭터·세계관·진행 방식을 정의
- **대화 메모리**: `InMemoryChatMessageHistory` + `RunnableWithMessageHistory`로 세션별 맥락 유지
- **LLM 교체 용이성**: `config.LLM_MODEL`을 `<provider>/<model>` 형식으로 지정. OpenAI ↔ Gemini ↔ 로컬 모델 단일 지점에서 교체
- **narrative-agnostic 인프라**: `chain.py`, `retriever.py`, `utils.py`는 5.18에 의존하지 않음. 다른 내러티브로 가져갈 때 `prompt.py` 본문 + `config.ENDING_MARKERS`만 교체

### 작업 순서

1. `uv add` 로 의존성 추가
2. `retriever.py` — PDF 로드(`PyPDFLoader`) → 텍스트 분할 → 임베딩 → FAISS 저장/로드
3. `prompt.py` — 제타 시스템 프롬프트 작성
4. `chain.py` — retriever + memory + LLM 조합으로 체인 구성
5. `main.py` — 대화 루프에서 체인 호출

## 문서화 규칙

작업 기록은 **세 파일로 분리**해 관리한다:

- **`bugs.md`** — 버그 수정 내역. 파일·문제·수정 방법·수정 전후 핵심 코드를 기록.
- **`features.md`** — 구현된 기능 목록(표)과 세부 설명. 보안 강화 내역도 이 파일 내 서브섹션에 포함.
- **`optimizations.md`** — 성능·품질·구조 개선 내용과 근거.

버그를 수정하거나 최적화를 진행한 경우, 반드시 해당 파일에 항목을 추가한다. 기능을 추가·변경한 경우 `features.md`의 표와 관련 서브섹션을 갱신한다.
