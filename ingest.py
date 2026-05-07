"""Build (or resume) the FAISS vectorstore from the source PDF.

The ingest pipeline:
  1. Load the PDF and split it into overlapping chunks.
  2. Embed each chunk via Gemini, in small batches with cooldowns between them
     to avoid hitting the per-minute rate limit.
  3. Save after every batch so a crash mid-run can be resumed without
     re-embedding completed chunks.

All tunable parameters live in ``config.py``.
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

load_dotenv()


def embed_with_retry(
    db: FAISS | None,
    batch: list[Document],
    embeddings: GoogleGenerativeAIEmbeddings,
) -> FAISS:
    """Embed one batch of documents with exponential backoff on rate-limit errors.

    Returns either a freshly created FAISS index (if ``db`` was None) or the
    same ``db`` mutated to include the new batch.
    """
    last_error: Exception | None = None
    for attempt in range(config.INGEST_MAX_RETRIES):
        try:
            if db is None:
                return FAISS.from_documents(batch, embeddings)
            db.add_documents(batch)
            return db
        except Exception as e:
            last_error = e
            if "429" not in str(e):
                raise
            wait = config.INGEST_RETRY_WAIT_SECONDS * (attempt + 1)
            print(f"    rate limit — {wait}초 대기 후 재시도...")
            time.sleep(wait)
    assert last_error is not None
    raise last_error


def build() -> None:
    """Run the full ingest pipeline. Idempotent: resumes from any previous run."""
    print(f"PDF 로드 중: {config.PDF_PATH}")
    loader = PyPDFLoader(config.PDF_PATH)
    docs = loader.load()
    print(f"  {len(docs)}페이지 로드 완료")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    print(f"  {len(chunks)}개 청크 생성")

    embeddings = GoogleGenerativeAIEmbeddings(model=config.EMBEDDING_MODEL)

    # 중간 저장된 벡터스토어가 있으면 이어서 처리
    start_idx = 0
    db: FAISS | None = None
    if os.path.exists(config.VECTORSTORE_PATH):
        print("기존 벡터스토어 발견 — 이어서 처리합니다.")
        db = FAISS.load_local(
            config.VECTORSTORE_PATH,
            embeddings,
            allow_dangerous_deserialization=True,
        )
        start_idx = db.index.ntotal
        print(f"  {start_idx}개 청크 이미 완료, {len(chunks) - start_idx}개 남음")

    print(
        f"임베딩 생성 중 (배치 {config.INGEST_BATCH_SIZE}개, "
        f"{config.INGEST_DELAY_SECONDS}초 간격)..."
    )
    for i in range(start_idx, len(chunks), config.INGEST_BATCH_SIZE):
        batch = chunks[i : i + config.INGEST_BATCH_SIZE]
        print(f"  [{i + len(batch)}/{len(chunks)}] 처리 중...")
        db = embed_with_retry(db, batch, embeddings)

        # 배치마다 중간 저장 — 크래시 시 재실행하면 여기서부터 이어진다
        db.save_local(config.VECTORSTORE_PATH)

        if i + config.INGEST_BATCH_SIZE < len(chunks):
            time.sleep(config.INGEST_DELAY_SECONDS)

    print(f"벡터스토어 저장 완료: {config.VECTORSTORE_PATH}/")


if __name__ == "__main__":
    build()
