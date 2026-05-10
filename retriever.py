"""FAISS-backed retriever for the ingested PDF.

Loads a vectorstore that ``ingest.py`` previously built and exposes it as a
LangChain retriever. The Gemini embedding override below is necessary because
``gemini-embedding-001`` does not implement the single-text ``embed_query``
endpoint expected by LangChain's default integration.
"""

from __future__ import annotations

import os

from langchain_community.vectorstores import FAISS
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_google_genai import GoogleGenerativeAIEmbeddings

import config


class GeminiEmbeddings(GoogleGenerativeAIEmbeddings):
    """Routes ``embed_query`` through ``embed_documents`` for ``gemini-embedding-001``."""

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def load_retriever(
    k: int = config.RETRIEVER_K,
    vectorstore_path: str = config.VECTORSTORE_PATH,
    embedding_model: str = config.EMBEDDING_MODEL,
) -> VectorStoreRetriever:
    """Load the persisted FAISS index and return a top-k retriever.

    Raises:
        FileNotFoundError: If the vectorstore directory does not exist. Build
            it first with ``uv run python ingest.py``.
    """
    if not os.path.exists(vectorstore_path):
        raise FileNotFoundError(
            f"벡터스토어가 없습니다 ({vectorstore_path}). "
            "먼저 'uv run python ingest.py'를 실행해 인덱스를 빌드하세요."
        )
    embeddings = GeminiEmbeddings(model=embedding_model)
    db = FAISS.load_local(
        vectorstore_path, embeddings, allow_dangerous_deserialization=True
    )
    return db.as_retriever(search_kwargs={"k": k})
