"""configure_logging: our own loggers must reach stdout, or outcome-only logs are moot."""

import io
import logging
from collections.abc import Iterator

import pytest

from app.logging_config import LOGGER_NAME, configure_logging


@pytest.fixture(autouse=True)
def clean_logger() -> Iterator[None]:
    logger = logging.getLogger(LOGGER_NAME)
    saved_handlers, saved_level = list(logger.handlers), logger.level
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    for handler in saved_handlers:
        logger.addHandler(handler)
    logger.setLevel(saved_level)


def test_info_records_from_our_loggers_are_written_to_the_stream() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    logging.getLogger("launchwise.analyze").info("analyze outcome=ok")
    logging.getLogger("launchwise.contact").warning("contact outcome=delivery_failed")
    text = stream.getvalue()
    assert "INFO launchwise.analyze: analyze outcome=ok" in text
    assert "WARNING launchwise.contact: contact outcome=delivery_failed" in text


def test_records_carry_a_timestamp() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    logging.getLogger("launchwise.analyze").info("x")
    assert stream.getvalue()[:4].isdigit()  # starts with the year


def test_calling_it_again_does_not_duplicate_output() -> None:
    first, second = io.StringIO(), io.StringIO()
    configure_logging(first)
    configure_logging(second)
    logging.getLogger("launchwise.analyze").info("once")
    assert first.getvalue() == ""  # the old handler was replaced, not kept
    assert second.getvalue().count("once") == 1
    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1


def test_other_libraries_are_not_pulled_in() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    logging.getLogger("some.other.library").info("not ours")
    assert "not ours" not in stream.getvalue()


def test_records_still_propagate_so_tests_and_future_handlers_can_see_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging(io.StringIO())
    with caplog.at_level(logging.INFO):
        logging.getLogger("launchwise.analyze").info("visible to caplog")
    assert "visible to caplog" in caplog.text


def test_create_app_turns_logging_on() -> None:
    from app.main import create_app
    from app.settings import Settings

    create_app(Settings(_env_file=None, app_env="test"))
    logger = logging.getLogger(LOGGER_NAME)
    assert logger.getEffectiveLevel() <= logging.INFO
    assert len(logger.handlers) == 1
