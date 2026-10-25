"""
Module: cli.py
Purpose: The `llmwatch` command-line entry point.
WHY: One installable command for running the server now, and for running eval
suites from CI later (`llmwatch eval run ...`).
"""

import argparse
import sys
from importlib.metadata import version


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "llmwatch.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=False,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmwatch", description=__doc__)
    parser.add_argument(
        "--version", action="version", version=f"llmwatch {version('llmwatch')}"
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="Reload on code changes")
    serve.set_defaults(func=_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
