import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from prompt import get_prompt, get_condense_prompt
from retriever import load_retriever

_sessions: dict[str, InMemoryChatMessageHistory] = {}

def _get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in _sessions:
        _sessions[session_id] = InMemoryChatMessageHistory()
    return _sessions[session_id]

def _clean_docs(docs):
    for doc in docs:
        text = doc.page_content
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        doc.page_content = text.strip()
    return docs

def build_chain(profile: str = "", model: str = "gemini-2.5-flash-lite", temperature: float = 0.6):
    llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)
    retriever = load_retriever()

    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, get_condense_prompt()
    )
    cleaned_retriever = history_aware_retriever | RunnableLambda(_clean_docs)

    qa_chain = create_stuff_documents_chain(
        llm,
        get_prompt(profile),
        document_prompt=PromptTemplate.from_template("{page_content}"),
        document_separator="\n\n",
        document_variable_name="context",
    )

    rag_chain = create_retrieval_chain(cleaned_retriever, qa_chain)

    return RunnableWithMessageHistory(
        rag_chain,
        _get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    )
