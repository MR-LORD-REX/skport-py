import asyncio
from urllib.parse import urlencode

import aiohttp
import pytest
from aiohttp import web

from skport.config import ClientConfig, Language, Protocol
from skport.errors import ConfigError, DecodeError, NetworkError
from skport.transport import (
    RawResponse,
    RetryPolicy,
    Transport,
    base_headers,
    compact_json,
    game_headers,
    retry_after_seconds,
    sign,
)


@pytest.mark.asyncio
async def test_transport_preserves_encoded_path_and_repeated_query_bytes(http_server):
    observed = []

    async def echo(request):
        observed.append(request.raw_path)
        return web.json_response({"code": 0, "data": {}}, headers={"Retry-After": "12"})

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", echo)
    host = await http_server(app)
    params = [("value", "a/b?c% +&"), ("repeated", "one"), ("repeated", "two")]
    transport = Transport(ClientConfig())
    try:
        response = await transport.request("GET", host + "/%2Fopaque", params=params)
        assert observed == ["/%2Fopaque?" + urlencode(params)]
        assert response.headers["Retry-After"] == "12"
        assert response.json() == {"code": 0, "data": {}}
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_transport_sends_same_compact_unicode_json_that_was_signed(http_server):
    observed = []

    async def echo(request):
        observed.append(await request.text())
        return web.json_response({"code": 0, "data": {}})

    app = web.Application()
    app.router.add_post("/write", echo)
    host = await http_server(app)
    body = compact_json({"name": "\u5b50", "count": 1})
    transport = Transport(ClientConfig())
    try:
        await transport.request(
            "POST", host + "/write", headers={"Content-Type": "application/json"}, body=body
        )
        assert observed == [body]
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_transport_returns_redirect_without_forwarding_credentials(http_server):
    count = 0

    async def redirect(request):
        nonlocal count
        count += 1
        raise web.HTTPFound("http://invalid.invalid/redirect")

    app = web.Application()
    app.router.add_get("/redirect", redirect)
    host = await http_server(app)
    transport = Transport(ClientConfig())
    try:
        response = await transport.request("GET", host + "/redirect", headers={"cred": "private-cred"})
        assert response.status == 302
        assert count == 1
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_transport_timeout_has_safe_context_and_original_cause(http_server):
    async def delayed(request):
        await asyncio.sleep(0.05)
        return web.json_response({"code": 0, "data": {}})

    app = web.Application()
    app.router.add_get("/delay", delayed)
    host = await http_server(app)
    transport = Transport(ClientConfig(timeout=0.01))
    try:
        with pytest.raises(NetworkError) as error:
            await transport.request("GET", host + "/delay", params={"token": "private-token"})
        assert error.value.path == "/delay"
        assert error.value.__cause__ is not None
        assert "private-token" not in str(error.value)
        assert "token=" not in str(error.value)
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_transport_close_respects_external_session_ownership():
    async with aiohttp.ClientSession() as session:
        transport = Transport(ClientConfig(), session)
        await transport.close()
        await transport.close()
        assert not session.closed
        with pytest.raises(ConfigError):
            _ = transport.session


@pytest.mark.asyncio
async def test_transport_owned_session_closes_once():
    transport = Transport(ClientConfig())
    session = transport.session
    await transport.close()
    await transport.close()
    assert session.closed


def test_malformed_json_raises_decode_error_without_body():
    response = RawResponse(200, "private-response-body")
    with pytest.raises(DecodeError) as error:
        response.json()
    assert error.value.status == 200
    assert "private-response-body" not in str(error.value)
    assert "private-response-body" not in repr(response)


def test_signer_reference_vector_and_header_order():
    signed = sign(
        "/api/v1/game/player/binding",
        "",
        "0123456789abcdef0123456789abcdef",
        timestamp="1794842554",
    )
    assert signed["sign"] == "4fe5e21c32a5e43d998a5e578e75adc7"
    assert list(base_headers("1")) == ["platform", "timestamp", "dId", "vName"]


@pytest.mark.parametrize(
    "value, expected", [("12", 12), ("-2", 0), ("nan", None), ("inf", None), ("bad", None), (None, None)]
)
def test_retry_after_delay_parsing(value, expected):
    assert retry_after_seconds(value) == expected


def test_retry_after_date_in_past_clamps_to_zero():
    assert retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT") == 0


def test_retry_policy_respects_server_delay_and_caps_local_backoff():
    policy = RetryPolicy(backoff=1, max_backoff=4, jitter=0)
    assert policy.delay(10) == 4
    assert policy.delay(1, retry_after=15) == 15


def test_signature_headers_keep_role_and_locale_scope_explicit():
    args = {
        "language": Language.JA,
        "protocol": Protocol(),
        "user_agent": "test-agent",
        "cred": "private-credential",
        "salt": "private-signing-key",
        "path": "/api/v1/game/cards",
    }
    public = game_headers(**args)
    owner = game_headers(**args, game_role="3_role_server")
    assert public.headers["sk-language"] == "ja"
    assert "sk-game-role" not in public.headers
    assert owner.headers["sk-game-role"] == "3_role_server"
    assert "private-" not in repr(public)


@pytest.mark.parametrize(
    "settings", [{"attempts": 0}, {"attempts": True}, {"backoff": -1}, {"jitter": float("inf")}]
)
def test_invalid_retry_settings_raise_typed_errors(settings):
    with pytest.raises(ConfigError):
        RetryPolicy(**settings)
