from __future__ import annotations

import argparse

import uvicorn

from .api import app
from .models import STATE_ATROPHIE, STATE_HYPERTROPHIE, STATE_IMPASSE, STATE_STABLE
from .rpc import serve_state_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TP bactérie gRPC")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    api_parser = subparsers.add_parser("api", help="Lance l'API web")
    api_parser.add_argument("--host", default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=8000)

    state_parser = subparsers.add_parser("state", help="Lance un pod d'etat")
    state_parser.add_argument("--state", choices=[STATE_STABLE, STATE_HYPERTROPHIE, STATE_ATROPHIE, STATE_IMPASSE], required=True)
    state_parser.add_argument("--grpc-port", type=int, required=True)
    state_parser.add_argument("--metrics-port", type=int, required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "api":
        uvicorn.run(app, host=args.host, port=args.port)
        return

    serve_state_service(args.state, args.grpc_port, args.metrics_port)


if __name__ == "__main__":
    main()
