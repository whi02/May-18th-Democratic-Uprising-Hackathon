import time
import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()

PDF_PATH = "518_data_v3.pdf"
VECTORSTORE_PATH = "vectorstore"
BATCH_SIZE = 5
DELAY_SECONDS = 15
RETRY_WAIT_SECONDS = 65

def embed_with_retry(db, batch, embeddings, attempt=0):
    try:
        if db is None:
            return FAISS.from_documents(batch, embeddings)
        else:
            db.add_documents(batch)
            return db
    except Exception as e:
        if "429" in str(e) and attempt < 3:
            wait = RETRY_WAIT_SECONDS * (attempt + 1)
            print(f"    rate limit — {wait}초 대기 후 재시도...")
            time.sleep(wait)
            return embed_with_retry(db, batch, embeddings, attempt + 1)
        raise

def build():
    print(f"PDF 로드 중: {PDF_PATH}")
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()
    print(f"  {len(docs)}페이지 로드 완료")

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    print(f"  {len(chunks)}개 청크 생성")

    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

    # 중간 저장된 벡터스토어가 있으면 이어서 처리
    start_idx = 0
    db = None
    if os.path.exists(VECTORSTORE_PATH):
        print("기존 벡터스토어 발견 — 이어서 처리합니다.")
        db = FAISS.load_local(VECTORSTORE_PATH, embeddings, allow_dangerous_deserialization=True)
        start_idx = db.index.ntotal
        print(f"  {start_idx}개 청크 이미 완료, {len(chunks) - start_idx}개 남음")

    print(f"임베딩 생성 중 (배치 {BATCH_SIZE}개, {DELAY_SECONDS}초 간격)...")
    for i in range(start_idx, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        print(f"  [{i + len(batch)}/{len(chunks)}] 처리 중...")
        db = embed_with_retry(db, batch, embeddings)

        # 배치마다 중간 저장
        db.save_local(VECTORSTORE_PATH)

        if i + BATCH_SIZE < len(chunks):
            time.sleep(DELAY_SECONDS)

    print(f"벡터스토어 저장 완료: {VECTORSTORE_PATH}/")

if __name__ == "__main__":
    build()
