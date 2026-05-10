# 최적화 내역

## 1. `ingest.py` — 배치 임베딩 + 딜레이로 Rate Limit 회피
한 번에 모든 청크를 요청하면 즉시 Rate Limit에 걸린다. 5개 단위 배치로 나누고 배치 사이에 15초 대기를 두어 API 한도 내에서 안정적으로 처리한다.

- `BATCH_SIZE = 5`, `DELAY_SECONDS = 15`

---

## 2. `chain.py` — `_clean_docs`로 검색 문서 품질 향상
PDF에서 추출한 텍스트에는 연속 개행, 중복 공백, 페이지 번호만 있는 줄(`^\s*\d+\s*$`)이 포함되어 있다. 이를 그대로 LLM 컨텍스트에 넣으면 불필요한 토큰을 낭비하고 답변 품질이 떨어진다.

세 가지 정규식으로 전처리해 컨텍스트 밀도를 높였다.

```python
text = re.sub(r'\n{3,}', '\n\n', text)
text = re.sub(r'[ \t]{2,}', ' ', text)
text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
```

---

## 3. `chain.py` — `history_aware_retriever`로 맥락 기반 검색
일반 retriever는 유저의 최신 입력만 보고 검색하므로, 대화 흐름에서 암묵적으로 참조하는 이전 맥락을 놓친다. `create_history_aware_retriever`와 `get_condense_prompt()`를 조합해, 검색 전에 대화 기록을 반영한 독립적인 질의를 생성한다.

---

## 4. `chain.py` — `document_prompt` 명시로 메타데이터 노출 방지
`create_stuff_documents_chain`의 기본 문서 포맷은 소스, 페이지 번호 등 메타데이터를 함께 출력한다. `document_prompt=PromptTemplate.from_template("{page_content}")`로 본문만 넘겨 프롬프트 길이와 노이즈를 줄였다.

---

## 5. `retriever.py` — `k=4`로 검색 문서 수 제한
검색 문서가 너무 많으면 컨텍스트 윈도우 낭비 및 LLM 혼란이 생긴다. 실험적으로 4개가 내러티브 품질과 응답 속도의 균형점으로 확인됐다.

```python
return db.as_retriever(search_kwargs={"k": 4})
```

---

## 6. `ingest.py` — 청크 파라미터 튜닝 (`chunk_size=800, chunk_overlap=100`)
- `chunk_size=800`: 역사 자료 특성상 맥락 단위가 길어 800자로 설정해 문장 중간 절단을 최소화했다.
- `chunk_overlap=100`: 청크 경계에서 관련 내용이 잘리지 않도록 100자 중첩을 두었다.

---

## 7. `main.py` — 스트리밍 출력 (`invoke` → `stream`)

`chain.invoke()`를 `chain.stream()`으로 교체해 LLM 응답이 청크 단위로 실시간 출력되도록 변경했다.

마커(`<<사망>>`, `<<생존>>`)는 응답 맨 끝에 붙으므로, 스트리밍 중 버퍼 끝 `_MARKER_BUF` 길이만큼 출력을 지연해 마커가 화면에 찍히지 않도록 처리했다.

```python
_MARKER_BUF = max(len(DEATH_MARKER), len(SURVIVAL_MARKER)) + 2

# 스트림 중: 마커 길이만큼 버퍼 보유, 나머지 즉시 출력
if len(buffer) > _MARKER_BUF:
    print(buffer[:-_MARKER_BUF], end="", flush=True)
    buffer = buffer[-_MARKER_BUF:]

# 스트림 종료 후: 버퍼에서 마커 제거 후 출력
tail = clean_marker(buffer)
```

---

## 8. 코드 범용화 리팩토링 — 다른 AI 개발자가 이해·재사용 가능한 구조로 정리

**문제**: 모델명·청크 크기·마커 문자열·재시도 횟수 등 매직넘버가 5개 파일에 흩어져 있었고, 마커 스트리밍·엔딩 감지·인젝션 sanitizer 같은 재사용 가능한 패턴이 `main.py`에 직접 박혀 있었다. 타입 힌트·docstring도 거의 없어 신규 개발자 진입이 어려웠다.

**최적화 내용**:

1. **`config.py` 신설** — 모든 설정값(모델·경로·청크·재시도·마커·필드 길이 제한 등)을 한 파일로 집중. 다른 내러티브로 갈아끼울 때 편집할 곳이 명확해졌다.

2. **`utils.py` 신설 — 재사용 가능한 유틸 추출**:
   - `StreamingBuffer`: 응답 끝의 control marker가 스트리밍 중 화면에 노출되지 않도록 버퍼링. 다른 RAG 챗봇에 그대로 이식 가능.
   - `EndingDetector`: 응답 tail에서 마커 감지. 마커→키 매핑 dict 주입식으로 구성해 narrative-agnostic.
   - `sanitize_prompt_field`: 프롬프트 인젝션 방지용 입력 정제 함수.

3. **타입 힌트 + docstring 전면 추가** — 모든 public 함수에 시그니처 타입과 한 줄 설명을 달아 호출부에서 의도가 즉시 드러나도록 했다.

4. **이름 정리**:
   - `ZETA_SYSTEM` → `NARRATIVE_SYSTEM_PROMPT` (의미 명확)
   - `_MARKER_BUF` 제거 (StreamingBuffer 내부로 흡수)
   - `DEATH_MARKER`/`SURVIVAL_MARKER` 모듈 상수 → `config.ENDING_MARKERS` dict

5. **`ingest.py` 재귀 → 루프** — `embed_with_retry`의 재귀 + accumulator 안티패턴을 명시적 for 루프로 교체.

6. **`README.md` 신설 + `.env.example` 추가** — 빠른 시작, 아키텍처, 설정 가이드, 다른 내러티브로 변경하는 법 문서화. API 키 노출 위험이 있던 `.env` 템플릿은 분리.

7. **에러 메시지 개선** — `retriever.py`의 `FileNotFoundError`가 `uv run python ingest.py`로 어떻게 복구할지 안내.

**전·후 비교 (마커 처리 핵심부)**:

```python
# 수정 전 — main.py에 직접 박혀 있음
_MARKER_BUF = max(len(DEATH_MARKER), len(SURVIVAL_MARKER)) + 2
buffer = ""
for chunk in chain.stream(...):
    piece = chunk["answer"]
    full_text += piece
    buffer += piece
    if len(buffer) > _MARKER_BUF:
        print(buffer[:-_MARKER_BUF], end="", flush=True)
        buffer = buffer[-_MARKER_BUF:]
tail = clean_marker(buffer)
```

```python
# 수정 후 — narrative-agnostic 유틸 사용
buffer = StreamingBuffer(config.ENDING_MARKERS.values())
for chunk in chain.stream(...):
    flushable = buffer.feed(chunk["answer"])
    if flushable:
        print(flushable, end="", flush=True)
print(buffer.flush_tail(), end="")
return buffer.full_text
```

**검증**: import 체크 + StreamingBuffer/EndingDetector/sanitize 단위 테스트 52건 전부 통과 + 실제 PDF(184 청크) 기반 5턴 대화에서 회귀 없음 확인.
