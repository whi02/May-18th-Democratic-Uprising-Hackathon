# 5.18 Interactive Narrative Chatbot

5.18 민주화운동을 배경으로 한 RAG 기반 인터랙티브 텍스트 어드벤처. 유저가 1980년 5월 광주의 한 시민이 되어 역사적 사건 속에서 반응·선택하며 이야기를 체험한다.

## Quick Start

```bash
# 1. 의존성 설치
uv sync

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 GOOGLE_API_KEY 입력

# 3. 벡터스토어 빌드 (최초 1회 또는 PDF 변경 시)
uv run python ingest.py

# 4. 대화 시작
uv run python main.py
```

## Architecture

```
main.py            ──► CLI 진입점, 대화 루프, 엔딩 처리
  ├── chain.py     ──► RAG 체인 조립 (history-aware retriever + stuff QA)
  │     ├── prompt.py     ──► 5.18 narrative 시스템 프롬프트
  │     └── retriever.py  ──► FAISS 벡터스토어 로더
  ├── utils.py     ──► StreamingBuffer / EndingDetector / sanitize_prompt_field
  └── config.py    ──► 모든 설정값 (모델·경로·청크 크기·재시도 등)

ingest.py          ──► PDF → 청크 → 임베딩 → FAISS 인덱스 빌드
```

런타임 흐름: 유저 입력 → condense 프롬프트가 standalone 쿼리로 재작성 → FAISS 검색 → 검색 결과 정제 → 시스템 프롬프트 + 컨텍스트 + 히스토리로 LLM 호출 → 스트리밍 출력 → 마커 감지로 엔딩 분기.

## Configuration

모든 튜닝 가능한 값은 `config.py` 한 곳에 모여 있다. 주요 항목:

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `LLM_MODEL` | `google_genai/gemini-2.5-flash-lite` | `<provider>/<name>` 형식. OpenAI 등으로 교체 가능 |
| `LLM_TEMPERATURE` | `0.6` | 창작성 vs 일관성 |
| `RETRIEVER_K` | `4` | 검색 문서 수 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `100` | PDF 청킹 파라미터 |
| `INGEST_BATCH_SIZE` / `INGEST_DELAY_SECONDS` | `5` / `15` | Gemini Embedding rate limit 회피 |
| `MAX_USER_INPUT_LEN` | `400` | 프롬프트 패딩 공격 방지 |
| `ENDING_MARKERS` | `{"death": "<<사망>>", "survival": "<<생존>>"}` | LLM이 응답 끝에 출력하는 종료 마커 |

## 다른 내러티브로 변경하기

1. `config.PDF_PATH`를 새 PDF로 변경
2. `prompt.py`의 `NARRATIVE_SYSTEM_PROMPT` 본문을 새 페르소나·세계관에 맞게 재작성
3. `config.ENDING_MARKERS`를 해당 내러티브에 맞게 교체 (예: `{"win": "<<WIN>>", "lose": "<<LOSE>>"}`)
4. `prompt.py`의 `DEATH_EPILOGUE_PROMPT`·`SURVIVAL_EPILOGUE_PROMPT`를 새 엔딩 맥락으로 교체
5. `main.py`의 `_EPILOGUE_PROMPTS`·`_EPILOGUE_LABELS` 매핑을 새 키에 맞게 갱신
6. `uv run python ingest.py`로 새 벡터스토어 빌드

`chain.py`, `retriever.py`, `utils.py`는 narrative-agnostic이므로 수정할 필요가 없다.

## 보안

유저 입력이 시스템 프롬프트에 흘러가는 모든 경로에 인젝션 방어가 적용되어 있다. 자세한 내용은 `research.md`의 **기능 → 보안 강화** 섹션 참고.

## 핵심 모듈 재사용

`utils.py`의 세 유틸은 narrative와 무관하게 다른 RAG 챗봇 프로젝트에 그대로 가져다 쓸 수 있다.

- `StreamingBuffer` — 응답 끝의 control marker가 화면에 노출되지 않도록 스트림 버퍼링
- `EndingDetector` — 응답 tail에서 등록된 마커 감지 (유저 입력으로 위조 불가)
- `sanitize_prompt_field` — 시스템 프롬프트에 삽입될 사용자 입력 정제

## 작업 기록

버그 수정·기능·최적화 내역은 `research.md` 참고.
