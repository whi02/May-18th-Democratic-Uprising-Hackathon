# CLAUDE.md

Claude Code 전용 가이드 — **오월의 증언** (5.18 민주화운동 체험형 AI 챗봇)

GitHub: https://github.com/whi02/May-18th-Democratic-Uprising-Hackathon  
마감: 2026-05-12 (배포 포함)  
담당자: 휘영 (전체 단독 개발), 민기 (AI 모듈 원작성)

---

## 프로젝트 개요

플레이어가 신분(이름/나이/직업/배경)을 설정하면, AI가 1980년 5월 18일~27일 광주의 실제 역사 사건 속에 플레이어를 던져 놓는 서바이벌 내러티브. 플레이어의 선택에 따라 **사망** 또는 **생존** 엔딩으로 갈라진다.

**컨셉**: 플레이어 = 광주 시민. 기자 취재 방식이 아니라 역사의 한복판에 있는 생존자.  
**스택**: LangChain + Gemini RAG + FastAPI + Vanilla JS  
**배포**: Render(백엔드) + GitHub Pages(프론트) 또는 Railway

---

## 실제 폴더 구조 (feat/ai-module 통합 후)

```
May-18th-Democratic-Uprising-Hackathon/
├── .env                        ← GOOGLE_API_KEY, DB_URL (절대 커밋 금지)
├── chain.py                    ← history-aware retriever + _clean_docs + stuff QA chain
├── prompt.py                   ← NARRATIVE_SYSTEM_PROMPT, CONDENSE_SYSTEM, 에필로그 프롬프트
├── retriever.py                ← FAISS 벡터스토어 로드 (config.py 경로 사용)
├── ingest.py                   ← PDF → 청킹(800/100) → 임베딩 → FAISS 저장
├── utils.py                    ← StreamingBuffer, EndingDetector, sanitize_prompt_field
├── config.py                   ← 모든 튜닝값 중앙화 (경로, 모델, 청크, 마커 등)
├── ai-module/
│   ├── main.py                 ← CLI 테스트용 대화 루프 (민기 원본)
│   ├── vectorstore/            ← FAISS 인덱스 (ingest.py 실행 후 생성)
│   └── 518_data_v3.pdf         ← RAG 소스 PDF (33MB)
├── backend/
│   ├── main.py                 ← FastAPI 앱 + lifespan + CORS
│   ├── routers/
│   │   ├── session.py          ← POST/GET/DELETE /sessions
│   │   └── chat.py             ← POST /sessions/{id}/chat, GET /sessions/{id}/messages
│   ├── models/db.py            ← SQLAlchemy 모델 (Session, Message)
│   ├── schemas/schema.py       ← Pydantic 스키마
│   └── services/chain_service.py ← chain 래퍼, 엔딩 감지, danger_delta 계산
└── frontend/
    └── index.html              ← 단일 파일 (HTML + Tailwind CSS + Vanilla JS)
```

> `chain.py`, `prompt.py`, `retriever.py`, `utils.py`, `config.py`는 **프로젝트 루트**에 위치.  
> `backend/services/chain_service.py`가 `sys.path`에 루트를 추가해서 임포트함.

---

## 실행 명령어

```bash
# 백엔드 실행 (루트 폴더에서)
uvicorn backend.main:app --reload

# 벡터스토어 최초 생성 (루트 폴더에서 실행, 30~60분 소요)
uv run python ingest.py

# AI 모듈 단독 CLI 테스트
uv run python ai-module/main.py
```

**환경변수** (루트 `.env`):
```
GOOGLE_API_KEY=<실제_구글_AI_API_키>
DB_URL=mysql+pymysql://root:<비밀번호>@localhost:3306/518db
```

---

## 화면 흐름

```
① 시작화면 → ② 신분 설정 → ③ 지도(학습용) → ④ 채팅 → ⑤ 엔딩
```

- **③ 지도**: 클릭 불가, 마우스오버 툴팁으로 장소 설명만 제공 (학습 목적)
- **④ 채팅 진입 시**: AI가 자동으로 첫 장면을 열어줌 (`sendAutoStart()` → `"시작"` 전송)

---

## 아키텍처 — 데이터 흐름

```
[프론트] POST /sessions/{id}/chat { message, location:"", character:"" }
    ↓
[chat.py] invoke_chain(session_id, profile_text, message, game_date, location, character)
    ↓
[chain_service.py] 헤더 포맷 payload → chain.invoke({"input": payload})
    ↓
[chain.py (루트)] history-aware retriever + _clean_docs + FAISS RAG + Gemini
    ↓
answer 텍스트 + <<사망>>/<<생존>> 마커 + 📅 날짜 패턴
    ↓
[chain_service.py] EndingDetector(tail-only) → ending 감지
                   compute_danger_delta() → danger_delta 계산
                   날짜 파싱 → next_date
    ↓
[chat.py] DB 업데이트, 에필로그 생성(ending 시), 응답 반환
    ↓
[프론트] 날짜 진행 바, 생존 확률 미터, 역사 카드, 엔딩 화면 처리
```

---

## 채팅 API 요청/응답

```json
// POST /sessions/{id}/chat 요청
{ "message": "도청을 지키겠습니다.", "location": "", "character": "" }

// 응답
{
  "status": "ok",
  "data": {
    "assistant_message": { "content": "AI 응답 텍스트..." },
    "ending": null,
    "epilogue": null,
    "game_date": 21,
    "session_status": "active",
    "danger_delta": -15
  }
}
```

---

## 엔딩 시스템

| 마커 | ending 값 | session status | 조건 |
|------|-----------|---------------|------|
| `<<사망>>` | `"사망"` | `"dead"` | AI가 죽음 장면 묘사 후 출력 |
| `<<생존>>` | `"생존"` | `"survived"` | 5월 27일 도달 또는 살아남는 결말 |

- 마커는 AI 응답 **맨 끝**에 단독 출력
- `EndingDetector` (tail-only 스캔)로 감지 — 유저 입력 오탐 방지
- 엔딩 감지 시 → `generate_epilogue()` → 별도 LLM 호출로 에필로그 생성

---

## 생존 확률 미터 (danger_delta)

`chain_service.compute_danger_delta(answer)` — AI 응답에서 위험도 분석:

| delta | 키워드 |
|-------|-------|
| -25 | 발포, 총격, 총탄, 총을 맞, 쓰러졌, 숨졌, 사망 |
| -15 | 체포, 구타, 폭행, 진압, 부상, 끌려, 피투성 |
| -5  | 시위, 저항, 격렬, 충돌, 맞섰, 대치 |
| +10 | 숨었, 피신, 탈출, 도망, 안전한, 몸을 피 |

프론트에서 `state.survivalPct`에 누적. 30% 이하 시 펄스 애니메이션 표시.

---

## 날짜 진행 시스템

- AI 응답에서 `📅 1980년 5월 OO일` 패턴 파싱 → `game_date` 업데이트
- 날짜 변경 감지 시 채팅창에 역사 카드 자동 삽입 (`HISTORY_EVENTS` 객체, 18~27일 매핑)
- DB `sessions.game_date` 컬럼으로 서버 동기화

---

## AI 응답 포맷 (채팅 렌더링)

AI는 아래 형식으로 응답. 프론트 `renderAssistantMessage()`가 파싱해 UI 분리 표시.

```
📅 1980년 5월 21일 (수) 오후 1시

**[나레이터]**: 장면 묘사 (회색 블록, 이탤릭)
**[윤상원]**: 실존 인물 대사 (빨간 테두리 말풍선)
**[주인공]**: 플레이어 행동 서술 (오른쪽 정렬, 플레이어 이름 표시)
```

> `**[주인공]**` 라벨 고정 — 프로필 이름을 라벨로 쓰지 않음 (`prompt.py` 규칙)

---

## payload 포맷 (chain_service → chain)

```python
# JSON 방식 금지 — condense가 항상 같은 쿼리 생성해 반복 응답 버그 발생
# 헤더 + 순수 텍스트 방식 사용
payload = f"[5월 21일]\n{user_message}"
```

---

## 프롬프트 인젝션 방어 (5종)

1. `sanitize_prompt_field()` — 프로필 필드 줄바꿈/헤더/태그 제거, 길이 제한
2. 시스템 프롬프트 `## 보안 원칙` 섹션 — jailbreak 시도를 나레이션으로 흘려보냄
3. `EndingDetector` tail-only 스캔 — 유저 입력 마커 위조 방지
4. condense 프롬프트 강화 — 역할 변경 시도 제거 후 행동 의도만 추출
5. 입력 길이 제한 400자 — 프롬프트 패딩 공격 차단

---

## DB 스키마 (sessions 테이블)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) | UUID |
| player_name | VARCHAR(50) | |
| player_age | INT | |
| player_job | VARCHAR(100) | 직업 + 배경 합산 입력 |
| profile_text | TEXT | AI 모듈 전달용 문자열 |
| game_date | INT | 현재 게임 날짜 (기본값 18) |
| status | ENUM | active / dead / survived / abandoned |

---

## research.md 자동 업데이트 규칙

아래 상황이 발생하면 **작업 완료 직후** 반드시 `research.md`를 업데이트한다. 별도 요청 없이 자동으로 수행한다.

| 상황 | 기록할 내용 |
|------|------------|
| 버그 발견 및 수정 | BUG-XX 항목: 증상, 원인, 해결 방법, 수정 파일 |
| 새 기능 추가 | FEAT-XX 항목: 동작 설명, 수정 파일 목록 |
| 아키텍처 변경 | 변경 전/후 구조, 변경 이유 |
| 배포 관련 결정 | 플랫폼 선택, 환경변수, 명령어 |
| 잠재적 이슈 발견 | 이슈 테이블에 추가 (위치, 내용, 심각도) |
| 이슈 해결 | 해당 이슈 항목에 **해결됨** 표시 및 해결 방법 기록 |

**형식 규칙:**
- 버그: `### BUG-XX: 제목 (날짜, 해결됨/미해결)`
- 기능: `### FEAT-XX: 제목 (날짜)`
- 날짜는 `YYYY-MM-DD` 형식

---

## 코딩 규칙

- Python: type hint 필수
- `.env` 값 하드코딩 절대 금지 (`GOOGLE_API_KEY`, `DB_URL`)
- API 응답 형식: `{"status": "ok", "data": ...}` 통일
- 주석: 한국어
- 에러 처리 필수 (404, 500)

---

## 배포 계획

### 백엔드 (Render 또는 Railway)
```
- Python 3.11+ 환경
- 환경변수: GOOGLE_API_KEY, DB_URL
- 시작 명령: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
- ai-module/vectorstore/ 폴더를 Git에 포함 (ingest.py 결과물)
- requirements.txt 또는 pyproject.toml 필요
```

### 프론트엔드 (GitHub Pages)
```
- frontend/index.html 단일 파일
- API_BASE 상수를 배포된 백엔드 URL로 변경
- GitHub Pages: Settings → Pages → Branch: main, Folder: /frontend
```

### 배포 전 체크리스트
- [ ] `ai-module/vectorstore/` 폴더가 생성되어 있는가 (ingest.py 완료)
- [ ] `.env`가 `.gitignore`에 포함되어 있는가
- [ ] `frontend/index.html`의 `API_BASE`가 배포 URL로 변경되었는가
- [ ] `backend/main.py` CORS에 프론트 배포 도메인이 허용되어 있는가
- [ ] MySQL → SQLite 전환 여부 결정 (Render 무료 플랜은 DB 별도)
- [ ] `ai-module/vectorstore/`와 `518_data_v3.pdf`가 `.gitignore`에서 제외되어 있는가

---

## 자가 검증 체크리스트

작업 완료 후 반드시 확인:

- [ ] API 응답 형식이 `{"status": "ok", "data": ...}` 인가
- [ ] type hint가 모든 함수에 적용되었는가
- [ ] `.env` 하드코딩된 값이 없는가
- [ ] 에러 처리가 포함되었는가 (404, 500)
- [ ] `chain_service.invoke_chain()`이 4-tuple `(answer, ending, next_date, danger_delta)` 반환하는가
- [ ] `ChatResponse`에 `danger_delta` 필드가 포함되어 있는가

---

## 현재 미완료 작업 (우선순위 순)

1. **[긴급] `ai-module/vectorstore/` 생성** — `uv run python ingest.py` (30~60분)
2. **[배포] requirements.txt 생성** — 배포 환경 의존성
3. **[배포] 백엔드 배포** — Render/Railway, 환경변수 설정
4. **[배포] 프론트 배포** — GitHub Pages, `API_BASE` 변경
5. **[선택] SQLite 전환** — 배포 환경에 MySQL 없으면 SQLite로 교체
