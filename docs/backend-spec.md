# Backend 설계 명세서

> 5.18 민주화운동 인터랙티브 챗봇 — 백엔드 설계안
> 최초 작성: 2026-05-04 | 변경 시 날짜 업데이트

---

## 기술 스택

- **Framework**: FastAPI
- **Python**: 3.11
- **DB**: MySQL 8.0
- **ORM**: SQLAlchemy (동기 방식)
- **DB Driver**: pymysql (aiomysql 사용 안 함)
- **AI 연동**: ai-module/chain.py의 build_chain() 직접 import

---

## 폴더 구조

```
backend/
├── main.py                # FastAPI app 진입점
├── routers/
│   ├── session.py         # 세션 생성/조회/삭제
│   └── chat.py            # 채팅 메시지 처리
├── models/
│   └── db.py              # SQLAlchemy 모델 + DB 연결
├── schemas/
│   └── schema.py          # Pydantic 요청/응답 스키마
├── services/
│   └── chain_service.py   # build_chain() 래퍼, 엔딩 감지 로직
└── .env                   # DB_URL, GOOGLE_API_KEY (gitignore)
```

---

## DB 테이블 설계

### sessions

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID v4 (session_id) |
| player_name | VARCHAR(50) | 플레이어 이름 |
| player_age | INT | 나이 |
| player_job | VARCHAR(100) | 직업 |
| profile_text | TEXT | build_chain()에 넘길 조합 문자열 |
| status | ENUM('active','dead','survived','abandoned') | 게임 진행 상태 |
| created_at | DATETIME | 세션 생성 시각 |
| ended_at | DATETIME NULL | 엔딩 도달 시각 |

> ⚠️ status 값 정의
> - `active`: 게임 진행 중
> - `dead`: 게임 내 사망 (<<사망>> 마커)
> - `survived`: 게임 내 생존 (<<생존>> 마커)
> - `abandoned`: 사용자가 직접 종료 (DELETE /sessions)

### messages

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGINT PK AUTO_INCREMENT | |
| session_id | VARCHAR(36) FK → sessions.id | |
| role | ENUM('user','assistant') | |
| content | TEXT | 메시지 본문 |
| has_ending_marker | TINYINT(1) | <<사망>>/<<생존>> 포함 여부 |
| created_at | DATETIME | |

---

## API 엔드포인트

### POST /sessions
새 게임 세션 시작. 플레이어 프로필을 받아 session_id 반환.

**Request:**
```json
{
  "player_name": "김철수",
  "player_age": 22,
  "player_job": "대학생"
}
```

**Response:**
```json
{
  "status": "ok",
  "data": { "session_id": "uuid-v4" }
}
```

---

### GET /sessions/{session_id}
세션 상태 조회.

**Response:**
```json
{
  "status": "ok",
  "data": {
    "session_id": "...",
    "player_name": "김철수",
    "status": "active",
    "created_at": "2026-05-04T10:00:00"
  }
}
```

---

### POST /sessions/{session_id}/chat
메시지를 chain에 전달하고 응답 반환. 엔딩 마커 감지 시 status 업데이트.

**Request:**
```json
{ "message": "저는 전남도청으로 향합니다" }
```

**Response (일반):**
```json
{
  "status": "ok",
  "data": {
    "answer": "...(내러티브 응답)...",
    "ending": null
  }
}
```

**Response (엔딩 도달):**
```json
{
  "status": "ok",
  "data": {
    "answer": "...(내러티브 응답)...",
    "ending": "death",
    "epilogue": "...(에필로그 텍스트)..."
  }
}
```

---

### GET /sessions/{session_id}/messages
전체 대화 기록 조회 (프론트 히스토리 복원용).

**Response:**
```json
{
  "status": "ok",
  "data": [
    { "role": "user", "content": "...", "created_at": "..." },
    { "role": "assistant", "content": "...", "created_at": "..." }
  ]
}
```

---

### DELETE /sessions/{session_id}
세션 강제 종료 (포기/나가기). status를 `abandoned`로 변경.

---

## chain_service 핵심 로직

```python
chain_store: Dict[str, RunnableWithMessageHistory] = {}  # 인메모리 chain 캐시

def get_or_create_chain(session_id, profile_text):
    if session_id not in chain_store:
        chain_store[session_id] = build_chain(profile=profile_text)
    return chain_store[session_id]

def invoke(session_id, profile_text, message):
    chain = get_or_create_chain(session_id, profile_text)
    config = {"configurable": {"session_id": session_id}}
    result = chain.invoke({"input": message}, config=config)
    answer = result["answer"]
    ending = None
    if "<<사망>>" in answer:
        ending = "death"
    elif "<<생존>>" in answer:
        ending = "survival"
    return answer, ending
```

> ⚠️ 주의: chain_store는 인메모리라 서버 재시작 시 초기화됨.
> sessions 테이블의 profile_text로 chain 재생성 가능하도록 설계됨.

---

## 에러 처리 기준

| 상황 | HTTP 코드 |
|------|-----------|
| session_id 없음 | 404 |
| chain 호출 실패 | 500 |
| 잘못된 요청 형식 | 422 (FastAPI 자동) |

---

## 환경변수 (.env)

```
GOOGLE_API_KEY=...
DB_URL=mysql+pymysql://user:password@localhost:3306/518db
```

---

## 구현 순서

1. `backend/models/db.py` — SQLAlchemy 모델 + DB 연결
2. `backend/schemas/schema.py` — Pydantic 스키마
3. `backend/services/chain_service.py` — build_chain() 래퍼
4. `backend/routers/session.py` — 세션 API
5. `backend/routers/chat.py` — 채팅 API
6. `backend/main.py` — FastAPI 앱 진입점

---

## 향후 개선 사항

- [ ] StreamingResponse 적용 (LLM 응답 실시간 출력)
- [ ] 서버 재시작 시 chain_store 자동 복원
- [ ] 요청 로깅 미들웨어 추가
