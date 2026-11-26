"""Public exceptions and context-sensitive response classification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SkportError(Exception):
    """Base SDK error carrying safe request context."""

    retryable = False

    def __init__(
        self,
        message: str = "",
        *,
        code: int | str | None = None,
        status: int | None = None,
        path: str = "",
        retry_after: float | None = None,
        attempt: int | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.path = path.split("?", 1)[0]
        self.retry_after = retry_after
        self.attempt = attempt
        self.context = dict(context or {})
        self.context.update(endpoint=self.path, status=status, api_code=code)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, status={self.status!r}, path={self.path!r})"


class ConfigError(SkportError):
    """Invalid input or client configuration."""


class NetworkError(SkportError):
    """A request failed before a complete HTTP response."""

    retryable = True


class AuthError(SkportError):
    """An account token or SKPORT credential was rejected."""


class APIError(SkportError):
    """An unsuccessful business or HTTP response."""


class ServerError(APIError):
    """A transient upstream server failure."""

    retryable = True


class RateLimitError(APIError):
    """A rate-limit response, optionally with a retry delay."""

    retryable = True


class AlreadyCheckedIn(APIError):
    """The attendance service explicitly reports an existing claim."""


class ForbiddenError(APIError):
    """The authenticated account is not permitted to perform this request."""


class PrivacyError(ForbiddenError):
    """The requested public information is explicitly hidden."""


class TargetNotFound(APIError):
    """No player or role matches the supplied target."""


class WikiNotFound(APIError):
    """No published wiki article exists for the requested ID and locale."""


class PoolExhausted(SkportError):
    """All public credential units failed or are cooling down."""


class TokenNotInPool(SkportError):
    """No existing credential unit matches the supplied token."""


class MappingError(SkportError):
    """A source entity does not resolve to one canonical asset."""


class AssetError(SkportError):
    """Canonical assets are unavailable or invalid."""


class UnsupportedFormula(SkportError):
    """A calculation formula has no verified implementation."""


class DecodeError(SkportError):
    """JSON or the expected response envelope is malformed."""


AUTH_PATHS = frozenset(
    {
        "/user/oauth2/v2/grant",
        "/web/v1/auth/refresh",
        "/web/v1/user/auth/generate_cred_by_code",
    }
)
RATE_LIMIT_CODES = frozenset({10002, 10003, 429})
TRANSIENT_STATUS = frozenset({408, 425, 500, 502, 503, 504})
ATTENDANCE_PATH = "/web/v1/game/endfield/attendance"


def envelope(payload: Any) -> tuple[int | str | None, str, Any]:
    """Extract the common OAuth or SKPORT envelope fields."""
    if not isinstance(payload, Mapping):
        raise DecodeError("expected a JSON response object")
    code = payload.get("code", payload.get("status"))
    return code, str(payload.get("message") or payload.get("msg") or ""), payload.get("data")


def check_envelope(
    payload: Any,
    *,
    status: int,
    path: str,
    method: str = "GET",
    target: bool = False,
    retry_after: float | None = None,
) -> Any:
    """Classify a response using its endpoint and operation, returning raw data.

    Server messages are not echoed: some services include credentials in diagnostics.
    """
    code = payload.get("code", payload.get("status")) if isinstance(payload, Mapping) else None
    context: dict[str, Any] = {"code": code, "status": status, "path": path, "retry_after": retry_after}
    if status == 401:
        raise AuthError("authentication rejected", **context)
    if status == 429 or code in RATE_LIMIT_CODES:
        raise RateLimitError("request rate limited", **context)
    if status in TRANSIENT_STATUS or status >= 500:
        raise ServerError("upstream server failure", **context)
    if status == 403:
        raise ForbiddenError("account is not permitted to perform this request", **context)
    if status == 404:
        raise TargetNotFound("requested endpoint or target was not found", **context)
    if not isinstance(payload, Mapping):
        raise DecodeError("expected a JSON response object", **context)
    if status == 200 and code == 0:
        if "data" not in payload:
            raise DecodeError("successful envelope is missing data", **context)
        return payload["data"]
    if path in AUTH_PATHS:
        raise AuthError("account token or credential rejected", **context)
    message = str(payload.get("message") or payload.get("msg") or "").casefold()
    if code == 10001 and any(
        text in message
        for text in (
            "login expired",
            "not logged",
            "登录",
            "session expired",
            "credential",
        )
    ):
        raise AuthError("SKPORT session rejected", **context)
    if any(text in message for text in ("privacy", "private", "not public", "hidden")):
        raise PrivacyError("requested information is hidden", **context)
    if code == 10001:
        if path == ATTENDANCE_PATH and method.upper() == "POST":
            if any(
                text in message
                for text in ("already", "重复", "已签到", "signed today", "do not sign in again")
            ):
                raise AlreadyCheckedIn("daily reward was already claimed", **context)
        if target and ("binding" in path or path.endswith("/user") or "not found" in message):
            raise TargetNotFound("no valid information found for target", **context)
    if code is None:
        raise DecodeError("response is missing its success code", **context)
    raise APIError("SKPORT request rejected", **context)


def is_success(payload: Any) -> bool:
    """Return whether a payload contains a recognized success envelope."""
    return isinstance(payload, Mapping) and payload.get("code", payload.get("status")) == 0


def is_transient(status: int, payload: Any = None) -> bool:
    """Return whether an idempotent request can retry this response."""
    code = payload.get("code") if isinstance(payload, Mapping) else None
    return status in TRANSIENT_STATUS or status == 429 or code in RATE_LIMIT_CODES
