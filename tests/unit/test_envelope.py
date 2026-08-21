"""The response envelope is what stops a backend fault from unmounting the Decky panel."""

import asyncio

import pytest
from envelope import ERROR_CODES, err, ok, safe, set_logger
from validation import ValidationError


def run(coro):
    return asyncio.run(coro)


class RecordingLogger:
    def __init__(self):
        self.exceptions = []

    def exception(self, message, *args):
        self.exceptions.append(message % args if args else message)


@pytest.fixture(autouse=True)
def _quiet_logger():
    logger = RecordingLogger()
    set_logger(logger)
    yield logger
    set_logger(None)


def test_ok_shape():
    assert ok({"a": 1}) == {"ok": True, "data": {"a": 1}, "error": None}


def test_ok_defaults_to_null_data():
    assert ok() == {"ok": True, "data": None, "error": None}


def test_err_shape():
    assert err("internal", "boom") == {
        "ok": False,
        "data": None,
        "error": {"code": "internal", "message": "boom"},
    }


def test_err_rejects_undeclared_codes():
    # Codes are API: an ad-hoc code cannot be documented in the troubleshooting page.
    with pytest.raises(KeyError):
        err("made_up_code", "boom")


def test_every_declared_code_is_usable():
    for code in ERROR_CODES:
        assert err(code, "x")["error"]["code"] == code


def test_safe_passes_through_a_successful_result():
    @safe
    async def method():
        return ok(42)

    assert run(method()) == {"ok": True, "data": 42, "error": None}


def test_safe_wraps_a_bare_return_value_in_an_envelope():
    @safe
    async def method():
        return 42

    assert run(method()) == {"ok": True, "data": 42, "error": None}


def test_safe_converts_validation_errors_into_validation_envelopes():
    @safe
    async def method():
        raise ValidationError("server_port", "must be between 1 and 65535")

    result = run(method())
    assert result["ok"] is False
    assert result["error"]["code"] == "validation"
    assert "server_port" in result["error"]["message"]


def test_safe_never_lets_an_exception_escape(_quiet_logger):
    @safe
    async def method():
        raise RuntimeError("internal detail with /home/bschelst/secret/path")

    result = run(method())
    assert result["ok"] is False
    assert result["error"]["code"] == "internal"
    # The traceback goes to the log, not to the UI.
    assert _quiet_logger.exceptions


def test_safe_does_not_leak_internal_detail_to_the_caller():
    @safe
    async def method():
        raise RuntimeError("/home/bschelst/.ssh/id_ed25519 could not be read")

    message = run(method())["error"]["message"]
    assert "id_ed25519" not in message
    assert "/home/bschelst" not in message


def test_safe_handles_cancellation_without_swallowing_it():
    # Swallowing CancelledError breaks task shutdown during _unload.
    @safe
    async def method():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        run(method())


def test_safe_preserves_the_method_name():
    @safe
    async def get_status():
        return ok()

    assert get_status.__name__ == "get_status"
