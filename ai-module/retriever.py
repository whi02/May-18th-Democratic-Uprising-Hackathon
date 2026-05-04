import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

VECTORSTORE_PATH = "vectorstore"

class GeminiEmbeddings(GoogleGenerativeAIEmbeddings):
    """embed_query를 embed_documents로 우회해 gemini-embedding-001 호환성 확보."""
    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

def load_retriever():
    if not os.path.exists(VECTORSTORE_PATH):
        raise FileNotFoundError(
            "벡터스토어가 없습니다. 먼저 'uv run python ingest.py'를 실행하세요."
        )
    embeddings = GeminiEmbeddings(model="models/gemini-embedding-001")
    db = FAISS.load_local(VECTORSTORE_PATH, embeddings, allow_dangerous_deserialization=True)
    return db.as_retriever(search_kwargs={"k": 4})
