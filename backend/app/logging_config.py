"""Make our own log lines visible. Nothing else is touched.

Python drops INFO records when no handler is configured, and uvicorn configures only its own
loggers. Without this, the outcome-only lines the contact and analyze code write would never reach
`docker compose logs`. Only the `launchwise` logger tree is configured. Those lines carry outcomes
and fixed codes, never visitor data (tests enforce that), so showing them is safe.
"""

import logging
import sys
from typing import TextIO

LOGGER_NAME = "launchwise"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(stream: TextIO | None = None) -> None:
    """Idempotent: calling it again replaces our handler instead of adding another."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # propagate stays True: records also reach the root logger, so tests and any future
    # handler see them. The root has no handlers in production, so nothing prints twice.
