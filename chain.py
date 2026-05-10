"""Builds the conversational RAG chain.

Pipeline:
    user_input + chat_history
        → history-aware retriever (rewrites question, fetches docs)
        → document cleaner (strips PDF artifacts)
        → stuff-documents QA chain (LLM answers with retrieved context)
        → message-history wrapper (per-session memory)

Swap the LLM by passing ``model=`` to ``build_chain``; the format is
``"<provider>/<model_name>"`` (e.g. ``"openai/gpt-4o-mini"``).
"""

from __future__ import annotations

import re

from langchain.chat_models import init_chat_model
from langchain_classic.chains import (
    create_history_aware_retriever,
    create_retrieval_chain,
)
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory

import config
from prompt import get_condense_prompt, get_prompt
from retriever import load_retriever

# Per-session message histories. Keyed by session_id; populated lazily by
# ``RunnableWithMessageHistory`` via ``_get_session_history``.
_sessions: dict[str, InMemoryChatMessageHistory] = {}


def _get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    """Return (or create) the in-memory chat history for the given session."""
    if session_id not in _sessions:
        _sessions[session_id] = InMemoryChatMessageHistory()
    return _sessions[session_id]


def _clean_docs(docs: list[Document]) -> list[Document]:
    """Strip PDF artifacts (excess newlines, runs of spaces, lone page numbers)
    from retrieved documents to keep the LLM context dense and relevant."""
    for doc in docs:
        text = doc.page_content
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
        doc.page_content = text.strip()
    return docs


def build_chain(
    profile: str = "",
    model: str = config.LLM_MODEL,
    temperature: float = config.LLM_TEMPERATURE,
) -> RunnableWithMessageHistory:
    """Assemble the full conversational RAG chain.

    Args:
        profile: Character/profile string injected into the system prompt.
        model: ``"<provider>/<model_name>"`` or a bare model name.
        temperature: Sampling temperature for the LLM.

    Returns:
        A runnable that accepts ``{"input": str}`` and a session-scoped config,
        and yields ``{"answer": str, ...}`` chunks when streamed.
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
        llm = init_chat_model(model_name, model_provider=provider, temperature=temperature)
    else:
        llm = init_chat_model(model, temperature=temperature)

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
