import json
import logging

from app.logging import setup_logging


def reset_logger() -> logging.Logger:
    logger = logging.getLogger("senji")
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    return logger


def test_log_output_is_valid_json_with_required_keys(capsys) -> None:
    reset_logger()
    logger = setup_logging("INFO")

    logger.info("hello")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert payload["level"] == "INFO"
    assert payload["module"] == "senji"
    assert payload["msg"] == "hello"
    assert payload["ts"]
    assert set(payload) == {"level", "module", "msg", "ts", "exc"}


def test_exception_info_included_in_exc_field(capsys) -> None:
    reset_logger()
    logger = setup_logging("ERROR")

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert payload["level"] == "ERROR"
    assert payload["msg"] == "failed"
    assert "ValueError: boom" in payload["exc"]


def test_different_module_names_produce_different_module_values(capsys) -> None:
    reset_logger()
    setup_logging("INFO")
    fetch_logger = logging.getLogger("senji.fetch")
    parse_logger = logging.getLogger("senji.parse")

    fetch_logger.info("fetch")
    parse_logger.info("parse")

    lines = capsys.readouterr().out.strip().splitlines()
    payloads = [json.loads(line) for line in lines]

    assert payloads[0]["module"] == "senji.fetch"
    assert payloads[1]["module"] == "senji.parse"


def test_exc_field_is_none_without_exception(capsys) -> None:
    reset_logger()
    logger = setup_logging("INFO")

    logger.warning("warn")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert payload["level"] == "WARNING"
    assert payload["exc"] is None
