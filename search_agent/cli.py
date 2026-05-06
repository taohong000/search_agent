from __future__ import annotations

import argparse

from .agent_loop import SearchAgent
from .config import Settings
from .logging_config import configure_logging, get_logger


def main(argv: list[str] | None = None) -> int:
    """CLI \u5165\u53e3\uff1a\u89e3\u6790\u547d\u4ee4\u884c\u53c2\u6570\uff0c\u521b\u5efa SearchAgent\uff0c\u6267\u884c\u95ee\u7b54\u5e76\u8f93\u51fa\u7ed3\u679c\u3002"""
    parser = argparse.ArgumentParser(prog="search-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask a question against local documents")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--web", action="store_true", help="Force web search")
    ask_parser.add_argument("--no-web", action="store_true", help="Disable web search")
    ask_parser.add_argument("--top-k", type=int, default=None)
    ask_parser.add_argument("--show-sources", action="store_true")
    ask_parser.add_argument("--config", default=None, help="Path to TOML config file")

    web_parser = subparsers.add_parser("web", help="Launch Gradio web UI")
    web_parser.add_argument("--config", default=None, help="Path to TOML config file")
    web_parser.add_argument("--host", default="0.0.0.0", help="Server host")
    web_parser.add_argument("--port", type=int, default=7860, help="Server port")

    args = parser.parse_args(argv)
    if args.command == "ask":
        # \u6839\u636e\u547d\u4ee4\u884c\u53c2\u6570\u786e\u5b9a\u7f51\u7edc\u641c\u7d22\u7b56\u7565\uff1aauto / always / never
        policy = "auto"
        if args.web:
            policy = "always"
        if args.no_web:
            policy = "never"

        settings = Settings.from_sources(args.config)
        configure_logging(
            enabled=settings.log_enabled,
            level=settings.log_level,
            file_path=settings.log_file,
        )
        logger = get_logger("cli")
        logger.info(
            "cli.ask start question=%r web_policy=%s top_k=%s config=%s data_dir=%s model=%s",
            args.question,
            policy,
            args.top_k or settings.top_k,
            args.config,
            settings.data_dir,
            settings.model,
        )
        agent = SearchAgent.from_settings(settings)
        result = agent.ask(args.question, web_policy=policy, top_k=args.top_k or settings.top_k)
        logger.info(
            "cli.ask done answerable=%s used_web=%s local_sources=%s web_sources=%s rounds=%s",
            result.answerable,
            result.used_web,
            len(result.local_sources),
            len(result.web_sources),
            len(result.search_rounds),
        )
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
    elif args.command == "web":
        from .web_ui import main as web_main
        web_main(config_path=args.config, server_name=args.host, server_port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
