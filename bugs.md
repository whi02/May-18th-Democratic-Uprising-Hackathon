# 버그 수정 내역

## 1. `retriever.py` — `embed_query` API 호환성 버그
**문제**: `gemini-embedding-001` 모델은 LangChain의 기본 `embed_query` 메서드를 직접 호환하지 않아, 검색 시 API 오류가 발생했다.

**수정**: `GeminiEmbeddings` 서브클래스를 만들어 `embed_query`를 `embed_documents([text])[0]`로 우회 처리했다.

```python
class GeminiEmbeddings(GoogleGenerativeAIEmbeddings):
    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
```

---

## 2. `ingest.py` — Rate Limit(429) 발생 시 프로세스 종료 버그
**문제**: Gemini Embedding API의 분당 요청 제한에 걸리면 예외가 그대로 전파되어 임베딩 프로세스 전체가 중단됐다.

**수정**: `embed_with_retry` 함수를 추가해 `429` 오류 발생 시 최대 3회, 지수 백오프(65초 × 시도 횟수)로 자동 재시도하도록 했다.

```python
def embed_with_retry(db, batch, embeddings, attempt=0):
    try:
        ...
    except Exception as e:
        if "429" in str(e) and attempt < 3:
            wait = RETRY_WAIT_SECONDS * (attempt + 1)
            time.sleep(wait)
            return embed_with_retry(db, batch, embeddings, attempt + 1)
        raise
```

---

## 3. `ingest.py` — 중간 종료 시 처음부터 재처리되는 버그
**문제**: 임베딩 도중 프로세스가 중단(네트워크 오류, 키보드 인터럽트 등)되면, 재실행 시 이미 처리한 청크도 처음부터 다시 임베딩했다.

**수정**: 배치마다 `db.save_local()`로 중간 저장하고, 재실행 시 `db.index.ntotal`로 이미 완료된 청크 수를 확인해 해당 인덱스부터 이어서 처리한다.

```python
if os.path.exists(VECTORSTORE_PATH):
    db = FAISS.load_local(...)
    start_idx = db.index.ntotal  # 이미 처리된 개수

for i in range(start_idx, len(chunks), BATCH_SIZE):
    ...
    db.save_local(VECTORSTORE_PATH)  # 배치마다 저장
```

---

## 4. `main.py` — LLM 일시 오류 시 대화 강제 종료 버그
**문제**: 체인 호출 중 Gemini 서버의 일시적 500/429 오류가 발생하면 예외가 사용자에게 그대로 노출되며 게임이 종료됐다.

**수정**: `stream_invoke`에 재시도 루프를 추가해 500·429 오류에 한해 10초 단위 점진적 대기 후 최대 3회 재시도한다.

```python
for attempt in range(retries):
    try:
        ...
    except Exception as e:
        if attempt < retries - 1 and ("500" in msg or "429" in msg):
            time.sleep(10 * (attempt + 1))
        else:
            raise
```

---

## 5. `main.py` — 종료 마커가 출력 텍스트에 노출되는 버그
**문제**: LLM이 `<<사망>>` 또는 `<<생존>>` 마커를 응답 텍스트에 포함하면, 해당 마커가 사용자 화면에 그대로 출력됐다.

**수정**: `clean_marker` 함수로 마커를 출력 전에 제거한다.

```python
def clean_marker(text: str) -> str:
    return text.replace(DEATH_MARKER, "").replace(SURVIVAL_MARKER, "").strip()
```

---

## 6. `prompt.py` — `{profile}` 템플릿 변수 충돌 버그
**문제**: `ZETA_SYSTEM`의 `{profile}` 자리표시자를 `ChatPromptTemplate`에 그대로 넘기면, LangChain이 `profile`을 별도 입력 변수로 파싱해 `invoke` 호출 시 키 누락 오류가 발생했다.

**수정**: `get_prompt()` 안에서 `ZETA_SYSTEM.replace("{profile}", profile)`로 문자열 치환을 먼저 수행한 뒤 템플릿을 생성한다.

```python
def get_prompt(profile: str = "") -> ChatPromptTemplate:
    system = ZETA_SYSTEM.replace("{profile}", profile or "특별한 설정 없음")
    return ChatPromptTemplate.from_messages([...])
```
