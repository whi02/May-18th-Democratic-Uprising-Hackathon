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

AI 모델 레이어만 담당하므로 아래 구조를 목표로 한다.

```
main.py              # 진입점 및 대화 루프
chain.py             # LangChain 체인 조립 (RAG 또는 ConversationChain)
retriever.py         # 518_data_v3.pdf → 벡터스토어 → Retriever
prompt.py            # 시스템 프롬프트 / PromptTemplate 정의
```

### 핵심 설계 방향

- **RAG 구조**: `518_data_v3.pdf`를 청킹·임베딩하여 FAISS 벡터스토어에 저장 → `RetrievalQA` 또는 `ConversationalRetrievalChain`으로 질의응답
- **제타 페르소나**: 시스템 프롬프트(`prompt.py`)에서 캐릭터 정의 — 말투, 지식 범위, 응답 스타일
- **대화 메모리**: `ConversationBufferMemory` 또는 `ConversationSummaryMemory`로 맥락 유지
- **LLM 교체 용이성**: LLM 인스턴스를 `chain.py` 한 곳에서 주입해 OpenAI ↔ 로컬 모델 교체 가능하게 유지

### 작업 순서

1. `uv add` 로 의존성 추가
2. `retriever.py` — PDF 로드(`PyPDFLoader`) → 텍스트 분할 → 임베딩 → FAISS 저장/로드
3. `prompt.py` — 제타 시스템 프롬프트 작성
4. `chain.py` — retriever + memory + LLM 조합으로 체인 구성
5. `main.py` — 대화 루프에서 체인 호출
