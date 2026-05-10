"""Reusable utilities for marker-aware streaming, ending detection, and prompt
injection sanitization.

These helpers are narrative-agnostic — drop them into any RAG chatbot that:
  - streams LLM output and uses control markers at the response tail
  - needs to detect a terminal state from the model's final tokens
  - inserts user-controlled text into a system prompt
"""

from __future__ import annotations

import re
from typing import Iterable


class StreamingBuffer:
    """Buffers the tail of a streaming response so trailing control markers are
    not flushed to the user's screen.

    The model is instructed to place control markers (e.g. ``<<DONE>>``) at the
    very end of its response. Without buffering, those markers would print
    character-by-character before the stream completes. ``StreamingBuffer``
    holds back ``buffer_size`` characters and only flushes once the stream ends,
    where the marker can be stripped cleanly.

    Example:
        buf = StreamingBuffer(markers=["<<END>>"])
        for chunk in llm.stream(...):
            flushable = buf.feed(chunk)
            print(flushable, end="", flush=True)
        print(buf.flush_tail(), end="")
        full_text = buf.full_text  # for post-stream marker detection
    """

    def __init__(self, markers: Iterable[str], extra_buffer: int = 2) -> None:
        markers = list(markers)
        if not markers:
            raise ValueError("StreamingBuffer requires at least one marker")
        self._markers: list[str] = markers
        # Hold back enough characters to fully contain any marker plus padding.
        self._hold_size: int = max(len(m) for m in markers) + extra_buffer
        self._buffer: str = ""
        self._full_text: str = ""

    def feed(self, chunk: str) -> str:
        """Append a streamed chunk and return the portion safe to flush now."""
        self._full_text += chunk
        self._buffer += chunk
        if len(self._buffer) <= self._hold_size:
            return ""
        flushable = self._buffer[: -self._hold_size]
        self._buffer = self._buffer[-self._hold_size :]
        return flushable

    def flush_tail(self) -> str:
        """Return whatever remains in the buffer with all markers stripped."""
        tail = self._buffer
        for marker in self._markers:
            tail = tail.replace(marker, "")
        self._buffer = ""
        return tail.strip()

    @property
    def full_text(self) -> str:
        """Complete response including markers (for downstream detection)."""
        return self._full_text


class EndingDetector:
    """Detects which terminal marker (if any) the LLM emitted at the response tail.

    Only the last ``len(marker) + tail_buffer`` characters are inspected so that
    user-quoted markers earlier in the text do not falsely trigger the ending.
    """

    def __init__(self, markers: dict[str, str], tail_buffer: int = 10) -> None:
        if not markers:
            raise ValueError("EndingDetector requires at least one marker")
        self._markers: dict[str, str] = dict(markers)
        self._tail_buffer: int = tail_buffer
        self._max_marker_len: int = max(len(m) for m in markers.values())

    def detect(self, text: str) -> str | None:
        """Return the ending key if a marker is found in the text tail, else None."""
        tail = text[-(self._max_marker_len + self._tail_buffer) :]
        for key, marker in self._markers.items():
            if marker in tail:
                return key
        return None


# Patterns that, if present in a user-supplied profile field, would let the
# field break out of its slot in the system prompt.
_HEADER_PATTERN = re.compile(r"#+\s")
_TAG_PATTERN = re.compile(r"<[^>]{0,60}>")


def sanitize_prompt_field(text: str, max_len: int) -> str:
    """Defang a user-supplied string before interpolating it into a system prompt.

    Defenses applied:
      - newlines collapsed (the most common system-prompt-escape vector)
      - markdown headers (``##``) and XML tags neutralized
      - braces replaced so LangChain template variables (``{context}``) cannot
        be smuggled in
      - hard length cap so a giant string cannot push real instructions out of
        the context window
    """
    text = text.replace("\n", " ").replace("\r", " ")
    text = _HEADER_PATTERN.sub("", text)
    text = _TAG_PATTERN.sub("", text)
    text = text.replace("{", "(").replace("}", ")")
    return text[:max_len].strip()
