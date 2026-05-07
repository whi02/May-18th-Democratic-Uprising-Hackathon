"""Project-wide configuration.

Edit this file to swap models, change paths, tune RAG parameters, or adapt the
project for a different narrative. Every magic number used by the runtime lives
here so other developers do not have to grep through five files.
"""

# --- Paths ---
VECTORSTORE_PATH = "vectorstore"
PDF_PATH = "518_data_v3.pdf"

# --- LLM ---
LLM_MODEL = "google_genai/gemini-2.5-flash-lite"
LLM_TEMPERATURE = 0.6

# --- Embedding & Retrieval ---
EMBEDDING_MODEL = "models/gemini-embedding-001"
RETRIEVER_K = 4

# --- Ingestion ---
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
INGEST_BATCH_SIZE = 5
INGEST_DELAY_SECONDS = 15
INGEST_RETRY_WAIT_SECONDS = 65
INGEST_MAX_RETRIES = 3

# --- Runtime resilience ---
LLM_MAX_RETRIES = 3
LLM_RETRY_BACKOFF_SECONDS = 10
LLM_RETRYABLE_ERRORS = ("500", "429")

# --- Input validation ---
MAX_USER_INPUT_LEN = 400
PROFILE_FIELD_LIMITS = {
    "name": 20,
    "age": 10,
    "occupation": 30,
    "background": 80,
}

# --- Narrative endings (project-specific) ---
# Map of internal ending key → marker string the LLM emits at the end of a response.
# Swap these for a different narrative (e.g. {"win": "<<WIN>>", "lose": "<<LOSE>>"}).
ENDING_MARKERS = {
    "death": "<<사망>>",
    "survival": "<<생존>>",
}

# Extra bytes beyond the longest marker that the tail-scan inspects.
# Allows for trailing whitespace / punctuation around the marker.
ENDING_TAIL_BUFFER = 10
