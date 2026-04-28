from __future__ import annotations

import argparse

from .agent_loop import SearchAgent
from .config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="search-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask a question against local documents")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--web", action="store_true", help="Force web search")
    ask_parser.add_argument("--no-web", action="store_true", help="Disable web search")
    ask_parser.add_argument("--top-k", type=int, default=None)
    ask_parser.add_argument("--show-sources", action="store_true")
    ask_parser.add_argument("--config", default=None, help="Path to TOML config file")

    args = parser.parse_args(argv)
    if args.command == "ask":
        policy = "auto"
        if args.web:
            policy = "always"
        if args.no_web:
            policy = "never"

        settings = Settings.from_sources(args.config)
        agent = SearchAgent.from_settings(settings)
        result = agent.ask(args.question, web_policy=policy, top_k=args.top_k or settings.top_k)
        print(result.answer)
        if args.show_sources:
            print("\n\u672c\u5730\u6765\u6e90:")
            for source in result.local_sources:
                print(f"- {source.title} | {source.path} | \u547d\u4e2d: {', '.join(source.matched_terms)}")
            print("\n\u7f51\u7edc\u6765\u6e90:")
            for source in result.web_sources:
                print(f"- {source.title} | {source.url}")
            print("\n\u7f51\u9875\u6b63\u6587:")
            for page in result.web_pages:
                print(f"- {page.title or page.url} | {page.provider} | {page.status} | {page.url}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
