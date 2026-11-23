from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skport.auth.credential import Credential
from skport.config import ClientConfig
from skport.errors import DecodeError, check_envelope
from skport.transport import RawResponse, Transport, account_headers, compact_json, retry_after_seconds

_GRANT = "/user/oauth2/v2/grant"
_CREDENTIAL = "/web/v1/user/auth/generate_cred_by_code"
_REFRESH = "/web/v1/auth/refresh"


class AuthFlow:
    """Exchange account tokens and renew reusable SKPORT signing keys."""

    def __init__(self, config: ClientConfig, transport: Transport) -> None:
        self.config = config
        self.transport = transport

    async def authenticate(self, token: str) -> Credential:
        """Authenticate with two requests, without loading game bindings.

        A grant code is consumed immediately. The resulting credential and
        signing key are the reusable intermediates retained by the token pool.
        """
        headers = account_headers(language=self.config.lang, user_agent=self.config.user_agent)
        grant_response = await self.transport.request(
            "POST",
            f"{self.config.hosts.account}{_GRANT}",
            headers=headers,
            body=compact_json({"appCode": self.config.protocol.app_code, "token": token, "type": 0}),
        )
        grant = self._data(grant_response, _GRANT)
        grant_code = self._required(grant, "code", _GRANT)
        response = await self.transport.request(
            "POST",
            f"{self.config.hosts.game}{_CREDENTIAL}",
            headers={
                **headers,
                "platform": self.config.protocol.platform,
                "vName": self.config.protocol.version,
            },
            body=compact_json({"kind": 1, "code": grant_code}),
        )
        data = self._data(response, _CREDENTIAL)
        return Credential(
            token=token,
            cred=self._required(data, "cred", _CREDENTIAL),
            salt=self._required(data, "token", _CREDENTIAL),
            user_id=str(data.get("userId") or ""),
            account_uid=str(grant.get("uid") or ""),
        )

    async def refresh(self, credential: Credential) -> Credential:
        """Renew the signing key using the existing credential.

        The refresh endpoint accepts cred without a signature, allowing
        renewal even after the old signing key stops being usable.
        """
        headers = {
            **account_headers(language=self.config.lang, user_agent=self.config.user_agent),
            "cred": credential.cred,
            "platform": self.config.protocol.platform,
            "vName": self.config.protocol.version,
        }
        response = await self.transport.request("GET", f"{self.config.hosts.game}{_REFRESH}", headers=headers)
        data = self._data(response, _REFRESH)
        credential.salt = self._required(data, "token", _REFRESH)
        credential.touch()
        return credential

    @staticmethod
    def _data(response: RawResponse, path: str) -> Mapping[str, Any]:
        delay = retry_after_seconds(
            response.headers.get("Retry-After") or response.headers.get("retry-after")
        )
        try:
            payload = response.json()
        except DecodeError:
            if response.status >= 400:
                check_envelope(None, status=response.status, path=path, retry_after=delay)
            raise
        if not isinstance(payload, Mapping):
            raise DecodeError("authentication response must be an object", status=response.status, path=path)
        data = check_envelope(payload, status=response.status, path=path, retry_after=delay)
        if not isinstance(data, Mapping):
            raise DecodeError(
                "authentication response data must be an object", status=response.status, path=path
            )
        return data

    @staticmethod
    def _required(data: Mapping[str, Any], key: str, path: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise DecodeError("authentication response is missing a required credential", path=path)
        return value
