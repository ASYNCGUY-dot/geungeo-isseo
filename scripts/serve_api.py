"""Run the local 근거있어 web app and API on the C003 snapshot.

The server binds to 127.0.0.1 by default, serves only local Host names unless more are allowed,
and keeps analyses only in memory.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from claimledger.api import create_app
from claimledger.snapshot import load_c003_snapshot, parse_aware_datetime

LOCAL_HOSTS = ("127.0.0.1", "localhost")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the 근거있어 web app and API")
    parser.add_argument("--source-export", type=Path, default=Path("data/c003-products.jsonl"))
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--allowed-host", action="append", default=[],
        help="extra Host name to serve besides 127.0.0.1 and localhost",
    )
    return parser.parse_args(argv)


def build_app(args: argparse.Namespace) -> FastAPI:
    retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
    return create_app(
        load_c003_snapshot(args.source_export, retrieved_at),
        source_retrieved_at=retrieved_at,
        allowed_hosts=(*LOCAL_HOSTS, *args.allowed_host),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    uvicorn.run(build_app(args), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
