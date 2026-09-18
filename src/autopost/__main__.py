"""Single entry point: `python -m autopost` (or the Docker CMD) starts the
content-pipeline scheduler and the dashboard web server together in one
process, sharing one DB connection and one LLM client."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

import uvicorn

from autopost.config import load_config
from autopost.db.repo import Database
from autopost.llm.client import LLMClient
from autopost.logging_setup import setup_logging
from autopost.scheduler.loop import run_all
from autopost.web.app import create_app

logger = logging.getLogger(__name__)


async def _serve_web(app, host: str, port: int) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def _run(settings) -> None:
    db = Database(settings.storage.db_path)
    llm = LLMClient(settings.llm)
    app = create_app(db, settings)
    try:
        await asyncio.gather(
            run_all(db, settings, llm),
            _serve_web(app, settings.web.host, settings.web.port),
        )
    finally:
        await llm.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="autopost")
    parser.add_argument(
        "--check-config", action="store_true",
        help="Load and print the resolved config (secrets redacted), then exit.",
    )
    args = parser.parse_args()

    settings = load_config()
    setup_logging(settings.logging.level)

    if args.check_config:
        print(json.dumps(settings.redacted(), indent=2))
        sys.exit(0)

    logger.info(
        "Starting autopost: niche=%s dashboard=http://%s:%s audit_status=%s",
        settings.niche.active_niche, settings.web.host, settings.web.port, settings.tiktok.audit_status,
    )
    try:
        asyncio.run(_run(settings))
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
