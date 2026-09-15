import json
import logging

import pytest

from utg_mcp.core.logging import (
    ContextFilter,
    RedactionFilter,
    request_id_var,
    setup_logging,
    tool_var,
    user_ref_var,
)

FAKE_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJvaWQiOiIxMjMifQ.c2lnbmF0dXJl"


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("utg_mcp.test", logging.INFO, __file__, 1, msg, args, None)


def test_redacts_jwt_and_bearer_from_message_and_args():
    record = _record("auth=%s raw=%s", "Bearer abc.def.ghi", FAKE_JWT)

    RedactionFilter().filter(record)

    rendered = record.getMessage()
    assert FAKE_JWT not in rendered
    assert "abc.def.ghi" not in rendered
    assert "Bearer [REDACTED]" in rendered


def test_redacts_attributes_with_sensitive_names():
    record = _record("obo")
    record.access_token = FAKE_JWT
    record.client_secret = "s3cr3t"
    record.status = 403

    RedactionFilter().filter(record)

    assert record.access_token == "[REDACTED]"
    assert record.client_secret == "[REDACTED]"
    assert record.status == 403


def test_context_filter_injects_request_context():
    tokens = (request_id_var.set("req-1"), user_ref_var.set("ref-1"), tool_var.set("diag_whoami"))
    try:
        record = _record("x")
        ContextFilter().filter(record)
    finally:
        tool_var.reset(tokens[2])
        user_ref_var.reset(tokens[1])
        request_id_var.reset(tokens[0])

    assert (record.request_id, record.user_ref, record.tool) == ("req-1", "ref-1", "diag_whoami")


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.mark.usefixtures("restore_root_logging")
def test_setup_logging_emits_redacted_json(capsys):
    setup_logging("INFO")
    token = request_id_var.set("req-42")
    try:
        logging.getLogger("utg_mcp.test").info("token recebido %s", FAKE_JWT, extra={"status": 200})
    finally:
        request_id_var.reset(token)

    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "utg_mcp.test"
    assert payload["request_id"] == "req-42"
    assert payload["status"] == 200
    assert FAKE_JWT not in line


@pytest.mark.usefixtures("restore_root_logging")
def test_setup_logging_routes_uvicorn_loggers_to_json_handler():
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.addHandler(logging.StreamHandler())
    uvicorn_error.propagate = False

    setup_logging("INFO")

    assert uvicorn_error.handlers == []
    assert uvicorn_error.propagate is True
