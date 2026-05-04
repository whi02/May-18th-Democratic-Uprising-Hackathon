import time
from dotenv import load_dotenv
from chain import build_chain
from prompt import DEATH_EPILOGUE_PROMPT, SURVIVAL_EPILOGUE_PROMPT

load_dotenv()

DEATH_MARKER = "<<사망>>"
SURVIVAL_MARKER = "<<생존>>"

def collect_profile() -> str:
    print("=== 당신의 프로필을 입력하세요 ===")
    name       = input("이름      : ").strip()
    age        = input("나이      : ").strip()
    occupation = input("직업      : ").strip()
    background = input("배경 (선택): ").strip()
    parts = [f"이름: {name}", f"나이: {age}", f"직업: {occupation}"]
    if background:
        parts.append(f"배경: {background}")
    print()
    return ", ".join(parts)

def invoke_with_retry(chain, payload, config, retries=3):
    for attempt in range(retries):
        try:
            return chain.invoke(payload, config=config)
        except Exception as e:
            msg = str(e)
            if attempt < retries - 1 and ("500" in msg or "429" in msg):
                wait = 10 * (attempt + 1)
                print(f"(서버 오류 - {wait}초 후 재시도...)")
                time.sleep(wait)
            else:
                raise

def check_ending(text: str) -> str | None:
    if DEATH_MARKER in text:
        return "death"
    if SURVIVAL_MARKER in text:
        return "survival"
    return None

def clean_marker(text: str) -> str:
    return text.replace(DEATH_MARKER, "").replace(SURVIVAL_MARKER, "").strip()

def show_epilogue(chain, config, ending_type: str):
    prompt = DEATH_EPILOGUE_PROMPT if ending_type == "death" else SURVIVAL_EPILOGUE_PROMPT
    print("\n" + "=" * 50)
    print("— 에필로그 —")
    print("=" * 50 + "\n")
    response = invoke_with_retry(chain, {"input": prompt}, config)
    print(response["answer"])
    print("\n" + "=" * 50)
    title = "[ END ]" if ending_type == "death" else "[ SURVIVED ]"
    print(f"           {title}")
    print("=" * 50 + "\n")

def main():
    profile = collect_profile()
    chain = build_chain(profile=profile)
    session_id = "default"
    config = {"configurable": {"session_id": session_id}}

    print("=== 1980년 5월, 광주 ===")
    print("(종료하려면 'q' 입력)\n")

    response = invoke_with_retry(chain, {"input": "시작"}, config)
    answer = response["answer"]
    ending = check_ending(answer)
    print(f"\n{clean_marker(answer)}\n")

    if ending:
        show_epilogue(chain, config, ending)
        return

    while True:
        user_input = input(">> ").strip()
        if user_input.lower() == "q":
            break
        if not user_input:
            continue

        response = invoke_with_retry(chain, {"input": user_input}, config)
        answer = response["answer"]
        ending = check_ending(answer)
        print(f"\n{clean_marker(answer)}\n")

        if ending:
            show_epilogue(chain, config, ending)
            break

if __name__ == "__main__":
    main()
