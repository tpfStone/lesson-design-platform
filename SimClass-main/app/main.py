"""SimClass MVP CLI 入口。

用法:
    python -m app.main [--debug] [--mock]

课堂自主推进 (Timeout τ) 通过 .env 配置:
    CLASSROOM_TIMEOUT_SECONDS=15   用户静默 τ 秒后 timeout 触发
    MAX_CONSECUTIVE_TIMEOUT_ACTIONS=3   连续超时自主推进的安全上限
"""
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="SimClass CLI MVP")
    parser.add_argument("--debug", action="store_true",
                        help="显示 Manager 的 reason 等调试信息")
    parser.add_argument("--mock", action="store_true",
                        help="强制使用 MockProvider（离线模式）")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if args.mock:
        from app.llm.mock import MockProvider
        llm = MockProvider()
        print("[SYSTEM] 使用 MockProvider（离线模式）运行。")
    else:
        from app.llm.provider import create_llm
        llm = create_llm()

    timeout_seconds = float(os.getenv("CLASSROOM_TIMEOUT_SECONDS", "15"))
    max_consecutive_timeouts = int(os.getenv("MAX_CONSECUTIVE_TIMEOUT_ACTIONS", "3"))

    from app.classroom.classroom import Classroom
    classroom = Classroom(llm=llm, debug=args.debug,
                          timeout_seconds=timeout_seconds,
                          max_consecutive_timeouts=max_consecutive_timeouts)
    classroom.run()


if __name__ == "__main__":
    main()
