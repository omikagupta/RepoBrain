"""Render entry point. Refuse to run the local profile on public ingress."""

import os

import uvicorn
from fastapi import FastAPI

from repobrain.main import create_app
from repobrain.settings import Settings


def deployed_app() -> FastAPI:
    try:
        settings = Settings(require_deployment_readiness=True)
        return create_app(settings)
    except (ValueError, OSError):
        raise RuntimeError("Hosted deployment configuration is invalid") from None


def main() -> None:
    raw = os.environ.get("PORT", "")
    if (
        not raw.isascii()
        or not raw.isdecimal()
        or len(raw) > 5
        or not 1 <= int(raw) <= 65535
    ):
        raise SystemExit("A valid PORT is required")
    uvicorn.run(
        "repobrain.hosted:deployed_app",
        factory=True,
        host="0.0.0.0",
        port=int(raw),
        access_log=False,
        proxy_headers=False,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
