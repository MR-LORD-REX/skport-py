import pytest
from aiohttp import web

from skport.auth import AuthFlow, Credential
from skport.config import ClientConfig, Hosts
from skport.errors import AuthError, DecodeError, RateLimitError, ServerError
from skport.transport import Transport


def use_hosts(monkeypatch, base):
    hosts = Hosts(account=base, game=base, binding=base, webview=base, news=base)
    monkeypatch.setattr(Hosts, "for_region", classmethod(lambda cls, region: hosts))


@pytest.mark.asyncio
async def test_authentication_is_two_requests_and_preserves_publisher_uid(http_server, monkeypatch):
    seen = []

    async def grant(request):
        seen.append((request.path, await request.json()))
        return web.json_response({"status": 0, "data": {"code": "grant-code", "uid": "G-account-uid"}})

    async def credential(request):
        seen.append((request.path, await request.json()))
        return web.json_response(
            {"code": 0, "data": {"cred": "credential", "token": "signing-key", "userId": "social-id"}}
        )

    app = web.Application()
    app.router.add_post("/user/oauth2/v2/grant", grant)
    app.router.add_post("/web/v1/user/auth/generate_cred_by_code", credential)
    base = await http_server(app)
    use_hosts(monkeypatch, base)
    config = ClientConfig(lang="ja")
    transport = Transport(config)
    try:
        result = await AuthFlow(config, transport).authenticate("account-token")
        assert len(seen) == 2
        assert seen[0][1] == {"appCode": config.protocol.app_code, "token": "account-token", "type": 0}
        assert seen[1][1] == {"kind": 1, "code": "grant-code"}
        assert result.account_uid == "G-account-uid"
        assert result.user_id == "social-id"
        assert result.cred == "credential"
        assert result.salt == "signing-key"
        assert not hasattr(result, "roles")
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_refresh_uses_credential_without_expired_signature(http_server, monkeypatch):
    observed = []

    async def refresh(request):
        observed.append(dict(request.headers))
        return web.json_response({"code": 0, "data": {"token": "fresh-signing-key"}})

    app = web.Application()
    app.router.add_get("/web/v1/auth/refresh", refresh)
    base = await http_server(app)
    use_hosts(monkeypatch, base)
    config = ClientConfig()
    transport = Transport(config)
    credential = Credential("account-token", "credential", "old-signing-key")
    try:
        result = await AuthFlow(config, transport).refresh(credential)
        assert result is credential
        assert result.salt == "fresh-signing-key"
        assert result.generation == 1
        headers = {key.lower(): value for key, value in observed[0].items()}
        assert headers["cred"] == "credential"
        assert "sign" not in headers
        assert "timestamp" not in headers
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, payload, expected",
    [
        (401, {"code": 10001, "message": "private-token", "data": {}}, AuthError),
        (200, {"code": 10001, "message": "private-token", "data": {}}, AuthError),
        (429, {"code": 429, "data": {}}, RateLimitError),
        (503, None, ServerError),
        (200, {"code": 0, "data": []}, DecodeError),
        (200, {"code": 0, "data": {}}, DecodeError),
    ],
)
async def test_auth_failures_have_typed_safe_errors(http_server, monkeypatch, status, payload, expected):
    async def refresh(request):
        if payload is None:
            return web.Response(status=status, text="private-response")
        return web.json_response(payload, status=status, headers={"Retry-After": "9"})

    app = web.Application()
    app.router.add_get("/web/v1/auth/refresh", refresh)
    base = await http_server(app)
    use_hosts(monkeypatch, base)
    config = ClientConfig()
    transport = Transport(config)
    try:
        with pytest.raises(expected) as failure:
            await AuthFlow(config, transport).refresh(Credential("token", "cred", "salt"))
        assert "private-" not in str(failure.value)
        if expected is RateLimitError:
            assert failure.value.retry_after == 9
    finally:
        await transport.close()
