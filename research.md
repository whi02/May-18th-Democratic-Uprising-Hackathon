# 오월의 증언 — 개발 리서치 노트

> 팀별로 작성. 백엔드/프론트엔드 경험, 최적화, 트러블슈팅, 결정 사항 기록.

---

## 백엔드 / 프론트엔드 (휘영)

### 현재 아키텍처 (2026-05-10 기준)

**화면 흐름:**
```
① 시작화면 → ② 신분 설정 → ③ 지도(학습용) → ④ 채팅 → ⑤ 엔딩
```

**데이터 흐름:**
```
[프론트] POST /sessions/{id}/chat { message, location:"", character:"" }
    ↓
[chat.py] invoke_chain(session_id, profile_text, message, game_date, location, character)
    ↓
[chain_service.py] 헤더 포맷 payload → chain.invoke({"input": payload})
    ↓
[chain.py (프로젝트 루트)] history-aware retriever + _clean_docs + FAISS RAG + Gemini
    ↓
answer 텍스트 + <<사망>>/<<생존>> 마커 + 📅 날짜 패턴
    ↓
[chain_service.py] 마커 감지 → ending, 날짜 파싱 → next_date
    ↓
[chat.py] DB 업데이트, 에필로그 생성, 응답 반환
    ↓
[프론트] 날짜 진행 바 업데이트, 엔딩 화면 처리
```

---

### 컨셉 변경 이력

**원래 컨셉 (초기):** 기자가 피해자·가해자를 취재하고 최종 리포트를 작성하는 방식. 엔딩 4종(발행/특종/탄압/실종).

**변경된 컨셉 (feat/ai-module, 민기, 2026-05-07):** 플레이어가 직업에 상관없이 1980년 5월 광주 시민이 되어 18일~27일을 체험하는 생존 내러티브. 엔딩 2종(사망/생존).

**변경 이유:** 민기가 AI 모듈을 전면 재작성하면서 프롬프트 컨셉 자체를 바꿈. 지도·인물 선택 등의 기자 UI는 이 세션에서 민기 컨셉에 맞게 정리됨 (지도는 학습용으로만 유지).

---

### 엔딩 마커 시스템 (현재)

| 마커 | ending 값 | session status | 조건 |
|------|-----------|---------------|------|
| `<<사망>>` | `"사망"` | `"dead"` | AI가 죽음 장면 묘사 후 출력 |
| `<<생존>>` | `"생존"` | `"survived"` | 5월 27일 도달 또는 살아남는 결말 |

- 마커는 AI 응답 맨 끝에 단독 출력됨
- `chain_service.py`가 마커를 감지하고 응답 텍스트에서 제거 후 반환
- 마커가 response body 전체에서 탐지됨 (보안 이슈: 유저 입력에 마커 포함 시 오탐 가능하나, 프롬프트 수준에서 방어 중)

---

### 날짜 진행 시스템

- AI 응답에서 `📅 1980년 5월 OO일` 패턴을 정규식으로 파싱해 날짜 추출
- 파싱된 날짜가 18~27 범위일 때만 반영
- DB `sessions.game_date`에 저장, 다음 요청 시 context header에 포함

---

### 백엔드 payload 포맷 (chain_service.py)

```python
# JSON 포맷 → 헤더 포맷으로 변경 (반복 응답 버그 수정 후)
header = "5월 18일"  # location/character 있으면 앞에 추가
payload = f"[{header}]\n{user_message}"
```

---

## 버그 & 트러블슈팅

### BUG-01: 채팅 시 "오류가 발생했습니다" (2026-05-10, 해결됨)

**증상:** 채팅 전송 시 항상 오류 메시지 표시

**원인 4가지 (모두 독립적으로 발생):**

1. **vectorstore 미생성**
   - `ai-module/vectorstore/` 폴더가 없으면 `load_retriever()`에서 `FileNotFoundError` 발생 → 500 에러
   - **해결:** `cd ai-module && uv run python ingest.py` 실행 (약 30~60분 소요, rate limit 대기 포함)

2. **faiss-cpu 미설치**
   - 백엔드 Python 환경에 `faiss-cpu` 패키지가 없으면 `Could not import faiss` 에러
   - **해결:** `pip install faiss-cpu`

3. **retriever.py 상대경로 문제**
   - `retriever.py`에서 `"vectorstore"` 상대경로 사용 시, uvicorn을 루트에서 실행하면 경로가 `project_root/vectorstore`로 잡힘
   - **해결:** `Path(__file__).parent / "vectorstore"` 절대경로로 수정

4. **프론트엔드 session_id 필드명 불일치**
   - 백엔드 응답: `json.data.id` (SessionResponse의 필드명)
   - 프론트엔드: `json.data.session_id`로 읽어서 항상 `undefined`
   - **해결:** `state.sessionId = json.data.session_id ?? json.data.id`

---

### BUG-02: AI가 항상 똑같은 응답 반복 (2026-05-10, 해결됨)

**증상:** 채팅할 때마다 AI가 동일한 응답을 반복 출력

**원인:** payload를 JSON 문자열로 감싸서 전달할 때, `history_aware_retriever`의 condense 단계가 매 턴 동일한 독립 쿼리를 생성 → 항상 같은 RAG 문서 검색 → 같은 응답

```python
# 문제 있던 코드
payload = json.dumps({"profile": ..., "message": ..., "game_date": ...})
# → condense가 "5.18 관련 질문"으로 항상 동일하게 재구성
```

**해결:** JSON 제거, 헤더 + 순수 텍스트 포맷으로 변경

```python
# 수정된 코드
payload = f"[{header}]\n{user_message}"
# → condense가 실제 유저 발언 기준으로 다양하게 재구성
```

---

### BUG-03: 특정 인물 선택해도 다른 인물이 답변 (2026-05-10, 부분 해결)

**증상:** 지도에서 전두환 선택 후 채팅 시 윤상원 등 다른 인물이 응답

**원인:** `character` 정보가 context header에만 포함되고 AI에게 해당 인물 중심으로 진행하라는 명시적 지시 없음

**해결 (부분):** payload에 인물 지시 문구 추가

```python
char_note = f"이 장면의 주요 등장인물은 {character}이다. {character}의 시각과 대사를 중심으로 장면을 구성해라.\n"
payload = f"[{header}]\n{char_note}{user_message}"
```

**현재 상태:** 지도가 학습용으로만 변경되어 character 선택 자체가 없어짐. 해당 버그는 더 이상 발생하지 않음.

---

### BUG-04: Windows 터미널 UnicodeEncodeError (2026-05-10, 무시)

**증상:** 백엔드 uvicorn 터미널에서 `UnicodeEncodeError: 'cp949' codec` 출력

**원인:** Windows 터미널 기본 인코딩(cp949)이 `📅` 같은 이모지를 출력하지 못함

**해결:** 실제 오류 아님 — 터미널 출력 문제일 뿐, 채팅 동작은 정상. 필요 시 `chcp 65001` 명령으로 UTF-8로 변경 가능.

---

## 신규 기능 (2026-05-11)

### FEAT-01: 생존 확률 미터

**위치:** 채팅 헤더 우측

**동작:**
- 게임 시작 시 100%
- AI 응답마다 `danger_delta` 계산 후 적용 (범위: 5% ~ 100%)
- 30% 이하 시 빨간색 펄스 애니메이션 + 색상 심화
- `danger_delta` 계산 기준 (chain_service.py의 `compute_danger_delta()`):
  - -25: 발포, 총격, 총탄, 총을 맞, 쓰러졌, 숨졌, 사망
  - -15: 체포, 구타, 폭행, 진압, 부상, 끌려, 피투성
  - -5:  시위, 저항, 격렬, 충돌, 맞섰, 대치
  - +10: 숨었, 피신, 탈출, 도망, 안전한, 몸을 피

**수정 파일:**
- `chain_service.py` — `compute_danger_delta()` 추가, `invoke_chain` 반환 타입 4-tuple로 변경
- `schema.py` — `ChatResponse.danger_delta: int = 0` 추가
- `chat.py` — `danger_delta` 언패킹 및 응답 포함
- `frontend/index.html` — 헤더 UI, `updateSurvivalMeter()`, state.survivalPct

---

### FEAT-02: 날짜별 역사 카드

**위치:** 채팅 메시지 영역, 날짜 전환 시 자동 삽입

**동작:**
- 채팅 시작 시 5월 18일 카드 표시
- AI 응답에서 `game_date`가 이전과 달라질 때 해당 날짜 카드 삽입
- 5월 18일 ~ 27일 각각 실제 역사 사건 텍스트 매핑 (JS `HISTORY_EVENTS` 객체)
- 파란색 그라데이션 카드 디자인 (학습용 앱 정체성 강화)

**수정 파일:**
- `frontend/index.html` — `HISTORY_EVENTS` 객체, `showHistoryCard()`, `enterChatScreen()`, `handleSendMessage()`에 날짜 변경 감지 로직

---

## 현재 알려진 잠재적 이슈

| 번호 | 위치 | 내용 | 심각도 |
|------|------|------|--------|
| 1 | `chain_service.py` | ~~엔딩 마커를 응답 전체에서 탐지 — 유저가 `<<사망>>`을 직접 입력하고 AI가 그대로 인용하면 오탐 가능~~ **해결 (2026-05-10)**: `EndingDetector` tail-only 스캔으로 교체, `config.ENDING_MARKERS` 중앙 참조 | 해결됨 |
| 2 | 백엔드 | 서버 재시작 시 인메모리 chain 캐시 초기화 — 재시작 후 첫 메시지에서 chain 재생성 (느릴 수 있음) | 낮음 |
| 3 | 백엔드 | ~~MySQL 연결 필요 — 배포 환경에서 MySQL 없으면 SQLite 전환 필요~~ **해결 (2026-05-11)**: SQLite로 전환 완료 | 해결됨 |
| 4 | `ingest.py` | Gemini Embedding API rate limit으로 배치 사이 15초 대기 — 전체 소요 약 30~60분 | 최초 1회만 |
| 5 | 프론트 | `handleRestart()` 시 `showScreen('intro')` 전 `state.gameDate = 18` 리셋하지만 `updateDateDisplay()` 호출 위치가 restart 이후여서 채팅 재진입 전까지는 날짜바가 리셋되지 않음 | 매우 낮음 |

---

## AI 모듈 (민기) 섹션

### 구조 변경 이력 (2026-05-10, feat/ai-module 통합)

**이전 구조:** `ai-module/chain.py`, `ai-module/prompt.py` 등 서브폴더에 위치

**현재 구조:** 프로젝트 루트에 위치 (민기 리팩토링 반영)
```
프로젝트 루트/
├── chain.py      — history-aware retriever + _clean_docs + stuff QA chain
├── prompt.py     — NARRATIVE_SYSTEM_PROMPT, CONDENSE_SYSTEM, 에필로그 프롬프트
├── retriever.py  — FAISS 벡터스토어 로드 (config.py 경로 사용)
├── ingest.py     — PDF → 청킹(800/100) → 임베딩 → FAISS 저장 (재시도 포함)
├── utils.py      — StreamingBuffer, EndingDetector, sanitize_prompt_field
├── config.py     — 모든 튜닝값 중앙화 (경로, 모델, 청크, 마커 등)
├── bugs.md       — 민기 버그 수정 내역
├── features.md   — 기능 명세
├── optimizations.md — 최적화 내역
└── ai-module/
    ├── vectorstore/  — ingest.py 실행 후 생성 (git에 포함 필요)
    └── 518_data_v3.pdf  — RAG 소스 (33MB)
```

**백엔드 연동 수정:** `chain_service.py`의 `sys.path`를 `ai-module/` → 프로젝트 루트로 변경
```python
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, _PROJECT_ROOT)
```

**config.py 경로 설정:**
```python
VECTORSTORE_PATH = "ai-module/vectorstore"  # uvicorn 루트 실행 기준
PDF_PATH = "ai-module/518_data_v3.pdf"
```

### 주요 개선 사항 (feat/ai-module)

1. **`config.py` 신설** — 모델명, 청크 크기, 마커, 재시도 횟수 등 모든 매직넘버 중앙화
2. **`utils.py` 신설** — `StreamingBuffer`, `EndingDetector`, `sanitize_prompt_field` 분리
3. **`chain.py` — `_clean_docs()` 추가** — PDF 노이즈(중복 개행, 페이지 번호 등) 전처리로 RAG 품질 향상
4. **`langchain_classic`** — `create_history_aware_retriever`, `create_retrieval_chain` 패키지 분리 대응
5. **`document_prompt` 명시** — 메타데이터(소스, 페이지 번호) 제거, 본문만 LLM에 전달

### 프롬프트 인젝션 방어 (5종)
1. `sanitize_prompt_field()` — 프로필 필드 줄바꿈/헤더/태그 제거, 길이 제한
2. 시스템 프롬프트 `## 보안 원칙` 섹션 — jailbreak 시도를 나레이션으로 흘려보냄
3. 엔딩 마커 tail 검사 (`EndingDetector`) — 응답 끝부분만 탐지해 유저 입력 위조 방지
4. condense 프롬프트 강화 — 역할 변경 시도 제거 후 행동 의도만 추출
5. 입력 길이 제한 400자 — 프롬프트 패딩 공격 차단

### 벡터스토어
- 소스: `ai-module/518_data_v3.pdf` (민기 작성, 33MB)
- 청킹: chunk_size=800, overlap=100
- 임베딩: `models/gemini-embedding-001`
- 검색: FAISS, k=4
- 생성 명령: `cd 프로젝트루트 && uv run python ingest.py` (약 30~60분)
