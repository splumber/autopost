import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # Quiet noisy third-party loggers unless we're at DEBUG.
    if level.upper() != "DEBUG":
        for noisy in ("httpx", "asyncio", "uvicorn.access"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
