"""CLI entry point for the interactive narrative chatbot.

Run with: ``uv run python main.py``

Flow:
    1. Collect a sanitized character profile from the user.
    2. Build the RAG chain bound to that profile.
    3. Stream the opening scene, then loop: user reaction → next scene.
    4. When the LLM emits a terminal marker (e.g. ``<<사망>>``), play the
       matching epilogue and exit.
"""

from __future__ import annotations

import time
from typing import Any

from dotenv import load_dotenv
from langchain_core.runnables import Runnable

import config
from chain import build_chain
from prompt import DEATH_EPILOGUE_PROMPT, SURVIVAL_EPILOGUE_PROMPT
from utils import EndingDetector, StreamingBuffer, sanitize_prompt_field

load_dotenv()

# ending key → epilogue prompt that the chain renders before the credits roll.
_EPILOGUE_PROMPTS: dict[str, str] = {
    "death": DEATH_EPILOGUE_PROMPT,
    "survival": SURVIVAL_EPILOGUE_PROMPT,
}

# ending key → label printed after the epilogue.
_EPILOGUE_LABELS: dict[str, str] = {
    "death": "[ END ]",
    "survival": "[ SURVIVED ]",
}


def collect_profile() -> str:
    """Prompt the user for character details and return a sanitized profile string."""
    print("=== 당신의 프로필을 입력하세요 ===")
    limits = config.PROFILE_FIELD_LIMITS
    name = sanitize_prompt_field(input("이름      : ").strip(), limits["name"])
    age = sanitize_prompt_field(input("나이      : ").strip(), limits["age"])
    occupation = sanitize_prompt_field(
        input("직업      : ").strip(), limits["occupation"]
    )
    background = sanitize_prompt_field(
        input("배경 (선택): ").strip(), limits["background"]
    )

    parts = [f"이름: {name}", f"나이: {age}", f"직업: {occupation}"]
    if background:
        parts.append(f"배경: {background}")
    print()
    return ", ".join(parts)


def stream_invoke(
    chain: Runnable,
    payload: dict[str, Any],
    config_obj: dict[str, Any],
) -> str:
    """Stream the chain output to stdout while hiding terminal markers.

    Retries on transient LLM errors (configurable via ``config.LLM_*``).
    Returns the full response text (markers included) so callers can detect
    endings via :class:`EndingDetector`.
    """
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            buffer = StreamingBuffer(config.ENDING_MARKERS.values())
            for chunk in chain.stream(payload, config=config_obj):
                if "answer" not in chunk:
                    continue
                flushable = buffer.feed(chunk["answer"])
                if flushable:
                    print(flushable, end="", flush=True)

            tail = buffer.flush_tail()
            if tail:
                print(tail, end="", flush=True)
            print()
            return buffer.full_text

        except Exception as e:
            msg = str(e)
            is_retryable = any(code in msg for code in config.LLM_RETRYABLE_ERRORS)
            if attempt < config.LLM_MAX_RETRIES - 1 and is_retryable:
                wait = config.LLM_RETRY_BACKOFF_SECONDS * (attempt + 1)
                print(f"\n(서버 오류 - {wait}초 후 재시도...)")
                time.sleep(wait)
            else:
                raise

    # Unreachable: the loop either returns or raises.
    raise RuntimeError("stream_invoke exhausted retries without raising")


def show_epilogue(
    chain: Runnable,
    config_obj: dict[str, Any],
    ending_key: str,
) -> None:
    """Render the epilogue for the given ending and print the closing label."""
    print("\n" + "=" * 50)
    print("— 에필로그 —")
    print("=" * 50 + "\n")
    stream_invoke(chain, {"input": _EPILOGUE_PROMPTS[ending_key]}, config_obj)
    print("\n" + "=" * 50)
    print(f"           {_EPILOGUE_LABELS[ending_key]}")
    print("=" * 50 + "\n")


def main() -> None:
    """Run the interactive narrative loop."""
    profile = collect_profile()
    chain = build_chain(profile=profile)
    runtime_config: dict[str, Any] = {"configurable": {"session_id": "default"}}
    detector = EndingDetector(config.ENDING_MARKERS, config.ENDING_TAIL_BUFFER)

    print("=== 1980년 5월, 광주 ===")
    print("(종료하려면 'q' 입력)\n")

    print()
    answer = stream_invoke(chain, {"input": "시작"}, runtime_config)
    print()

    ending = detector.detect(answer)
    if ending:
        show_epilogue(chain, runtime_config, ending)
        return

    while True:
        user_input = input(">> ").strip()
        if user_input.lower() == "q":
            break
        if not user_input:
            continue
        if len(user_input) > config.MAX_USER_INPUT_LEN:
            print(
                f"(입력이 너무 깁니다. {config.MAX_USER_INPUT_LEN}자 이내로 입력해주세요.)\n"
            )
            continue

        print()
        answer = stream_invoke(chain, {"input": user_input}, runtime_config)
        print()

        ending = detector.detect(answer)
        if ending:
            show_epilogue(chain, runtime_config, ending)
            break


if __name__ == "__main__":
    main()
