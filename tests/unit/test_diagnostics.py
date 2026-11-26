"""Error mapping and safe logging contracts."""

import logging

import pytest

from skport.errors import (
    AlreadyCheckedIn,
    APIError,
    AuthError,
    DecodeError,
    ForbiddenError,
    PrivacyError,
    RateLimitError,
    ServerError,
    TargetNotFound,
    check_envelope,
)
from skport.logging import RedactionFilter, get_logger, redact_headers


@pytest.mark.parametrize(
    "status,cls",
    [
        (401, AuthError),
        (403, ForbiddenError),
        (404, TargetNotFound),
        (429, RateLimitError),
        (503, ServerError),
    ],
)
def test_http_classification_includes_context(status, cls):
    with pytest.raises(cls) as error:
        check_envelope(None, status=status, path="/example", retry_after=2.5)
    assert error.value.status == status
    assert error.value.path == "/example"
    assert error.value.retry_after == 2.5


def test_same_business_code_has_distinct_endpoint_meanings():
    payload = {"code": 10001, "message": "No valid user information found"}
    with pytest.raises(TargetNotFound):
        check_envelope(payload, status=200, path="/api/v1/game/player/binding", target=True)
    with pytest.raises(APIError):
        check_envelope(payload, status=200, path="/unrecognized")
    with pytest.raises(AuthError):
        check_envelope(payload, status=200, path="/web/v1/auth/refresh")
    with pytest.raises(AlreadyCheckedIn):
        check_envelope(
            {"code": 10001, "message": "Already signed today"},
            status=200,
            path="/web/v1/game/endfield/attendance",
            method="POST",
        )


def test_raw_lists_and_none_are_preserved_but_malformed_envelopes_fail():
    assert check_envelope({"code": 0, "data": [1]}, status=200, path="/x") == [1]
    assert check_envelope({"code": 0, "data": None}, status=200, path="/x") is None
    for payload in ({"code": 0}, {}, []):
        with pytest.raises(DecodeError):
            check_envelope(payload, status=200, path="/x")


@pytest.mark.parametrize(
    "message,cls",
    [
        ("Login expired", AuthError),
        ("This profile is private", PrivacyError),
        ("No valid user information found", TargetNotFound),
    ],
)
def test_expiry_and_privacy_signals_precede_missing_target_context(message, cls):
    with pytest.raises(cls):
        check_envelope(
            {"code": 10001, "message": message},
            status=200,
            path="/api/v1/game/player/binding",
            target=True,
        )


def test_log_filter_redacts_dict_headers_and_query_without_touching_root():
    before = list(logging.getLogger().handlers)
    record = logging.LogRecord(
        "skport",
        logging.DEBUG,
        "",
        1,
        """request https://example.invalid/path?token=query-secret {'cred': 'cred-secret', "salt": "salt-secret"} sign=sign-secret Cookie: 'cookie-secret'""",
        (),
        None,
    )
    assert RedactionFilter().filter(record)
    assert all(
        secret not in record.getMessage()
        for secret in (
            "query-secret",
            "cred-secret",
            "salt-secret",
            "sign-secret",
            "cookie-secret",
        )
    )
    assert "https://example.invalid/path" in record.getMessage()
    get_logger("api")
    assert logging.getLogger().handlers == before
    assert redact_headers({"Authorization": "secret", "salt": "secret", "Accept": "json"}) == {
        "Authorization": "<redacted>",
        "salt": "<redacted>",
        "Accept": "json",
    }
