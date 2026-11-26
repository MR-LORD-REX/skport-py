"""HTTP-boundary regressions for the shared request engine."""

import asyncio
from collections import Counter

import pytest
import pytest_asyncio
from aiohttp import web

from skport import ClientConfig, SkportAPI
from skport.config import Hosts
from skport.errors import ConfigError, DecodeError, ServerError, TargetNotFound
from skport.transport import RetryPolicy, sign


@pytest_asyncio.fixture
async def api_server(http_server, monkeypatch):
    apis = []

    async def start(hook=None, tokens=("a", "b"), refresh_status=200):
        state = {"grants": 0, "refreshes": 0, "reads": Counter(), "salt": "fixture-key"}

        async def handler(request):
            if request.path == "/user/oauth2/v2/grant":
                state["grants"] += 1
                body = await request.json()
                return web.json_response({"status": 0, "data": {"code": body["token"], "uid": "owner"}})
            if request.path == "/web/v1/user/auth/generate_cred_by_code":
                body = await request.json()
                return web.json_response(
                    {
                        "code": 0,
                        "data": {
                            "cred": "cred-" + body["code"],
                            "token": state["salt"],
                            "userId": "provider",
                        },
                    }
                )
            if request.path == "/web/v1/auth/refresh":
                state["refreshes"] += 1
                assert "sign" not in request.headers
                if refresh_status != 200:
                    return web.json_response({"code": 10001}, status=refresh_status)
                state["salt"] = "renewed-key"
                return web.json_response({"code": 0, "data": {"token": state["salt"]}})
            query = request.raw_path.partition("?")[2]
            body = query if request.method == "GET" else await request.text()
            expected = sign(request.path, body, state["salt"], timestamp=request.headers["timestamp"])
            assert request.headers["sign"] == expected["sign"]
            state["reads"][request.path] += 1
            if hook is not None:
                result = await hook(request, state)
                if result is not None:
                    return result
            return web.json_response(
                {
                    "code": 0,
                    "data": {
                        "account": request.headers["cred"],
                        "language": request.headers["sk-language"],
                        "query": query,
                    },
                }
            )

        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", handler)
        url = await http_server(app)
        monkeypatch.setattr(ClientConfig, "hosts", property(lambda self: Hosts(url, url, url, url, url)))
        api = SkportAPI(tokens, retry=RetryPolicy(backoff=0, jitter=0))
        apis.append(api)
        return api, state

    yield start
    for api in apis:
        await api.close()


async def test_account_and_language_cache_isolation(api_server):
    api, state = await api_server()
    a = await api.user(token="a")
    b = await api.user(token="b")
    ja = await api.with_language("ja").user(token="a")
    assert a["account"] != b["account"]
    assert ja["language"] == "ja"
    a["account"] = "changed by caller"
    assert (await api.user(token="a"))["account"] == "cred-a"
    assert state["reads"]["/api/v2/user"] == 3
    assert state["grants"] == 2
    assert api.config.lang.value == "en"


async def test_encoded_query_matches_signed_bytes(api_server):
    api, _ = await api_server()
    data = await api.request("GET", "/echo", params={"term": ["a b", "伊馮", "+/"], "empty": ""})
    assert data["query"] == "term=a+b&term=%E4%BC%8A%E9%A6%AE&term=%2B%2F&empty="


async def test_stale_salt_refreshes_then_replays_same_owner(api_server):
    async def stale(request, state):
        if state["reads"][request.path] == 1:
            return web.json_response({"code": 10001}, status=401)

    api, state = await api_server(stale)
    result = await api.request("GET", "/data", token="owner", ttl=0)
    assert result["account"] == "cred-owner"
    assert state["grants"] == 1
    assert state["refreshes"] == 1
    assert state["reads"]["/data"] == 2


async def test_rejected_credential_falls_back_to_full_auth_same_owner(api_server):
    async def stale(request, state):
        if state["reads"][request.path] == 1:
            return web.json_response({}, status=401)

    api, state = await api_server(stale, refresh_status=401)
    assert (await api.request("GET", "/data", token="owner", ttl=0))["account"] == "cred-owner"
    assert state["grants"] == 2
    assert state["refreshes"] == 1


async def test_missing_target_never_reauthenticates(api_server):
    async def missing(request, state):
        return web.json_response({"code": 10001, "message": "No valid user information found"})

    api, state = await api_server(missing)
    with pytest.raises(TargetNotFound):
        await api.binding(skport_id="missing")
    assert state["grants"] == 1
    assert state["refreshes"] == 0
    assert state["reads"]["/api/v1/game/player/binding"] == 1


async def test_post_server_failure_is_never_replayed(api_server):
    async def unavailable(request, state):
        return web.Response(status=503, text="temporarily unavailable")

    api, state = await api_server(unavailable)
    with pytest.raises(ServerError):
        await api.request("POST", "/action", token="owner", payload={})
    assert state["reads"]["/action"] == 1


async def test_successful_write_invalidates_owner_cache(api_server):
    api, state = await api_server()
    await api.request("GET", "/attendance", token="a")
    await api.request("GET", "/attendance", token="b")
    await api.request("POST", "/action", token="a", payload={})
    await api.request("GET", "/attendance", token="a")
    await api.request("GET", "/attendance", token="b")
    assert state["reads"]["/attendance"] == 3


async def test_http_gate_limits_each_token_but_allows_different_tokens(api_server):
    active = Counter()
    maximum = Counter()
    total = [0, 0]

    async def slow(request, state):
        account = request.headers["cred"]
        active[account] += 1
        maximum[account] = max(maximum[account], active[account])
        total[0] += 1
        total[1] = max(total)
        await asyncio.sleep(0.005)
        active[account] -= 1
        total[0] -= 1

    api, _ = await api_server(slow, tokens=("a", "b", "c"))
    await asyncio.gather(*(api.request("GET", "/read", ttl=0) for _ in range(18)))
    assert set(maximum.values()) == {1}
    assert total[1] == 3


async def test_malformed_json_is_not_retried(api_server):
    async def malformed(request, state):
        return web.Response(text="{not json")

    api, state = await api_server(malformed)
    with pytest.raises(DecodeError):
        await api.request("GET", "/malformed", ttl=0)
    assert state["reads"]["/malformed"] == 1


async def test_locale_view_close_preserves_parent_then_parent_closes_view(api_server):
    api, _ = await api_server()
    view = api.with_language("ko")
    await view.close()
    assert (await view.request("GET", "/echo"))["language"] == "ko"
    await api.close()
    with pytest.raises(ConfigError):
        await view.request("GET", "/echo")


async def test_close_waits_for_operation_not_entire_worker_lifetime(api_server):
    started = asyncio.Event()
    release = asyncio.Event()
    idle = asyncio.Event()

    async def slow(request, state):
        started.set()
        await release.wait()

    api, _ = await api_server(slow)

    async def worker():
        await api.request("GET", "/slow", ttl=0)
        await idle.wait()

    task = asyncio.create_task(worker())
    await started.wait()
    closing = asyncio.create_task(api.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    await asyncio.wait_for(closing, 1)
    assert not task.done()
    idle.set()
    await task


async def test_read_retries_rate_limit_with_server_delay(api_server):
    delays = []

    class RecordingRetry(RetryPolicy):
        async def sleep(self, attempt, retry_after=None):
            delays.append(retry_after)

    async def limited(request, state):
        if state["reads"][request.path] == 1:
            return web.Response(status=429, headers={"Retry-After": "1.5"})

    api, state = await api_server(limited)
    api.retry = RecordingRetry()
    await api.request("GET", "/limited", ttl=0)
    assert state["reads"]["/limited"] == 2
    assert delays == [1.5]


async def test_cancelled_close_does_not_cancel_operation_completion(api_server):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(request, state):
        started.set()
        await release.wait()

    api, _ = await api_server(slow)
    read = asyncio.create_task(api.request("GET", "/slow", ttl=0))
    await started.wait()
    closing = asyncio.create_task(api.close())
    await asyncio.sleep(0)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    retry = asyncio.create_task(api.close())
    await asyncio.sleep(0)
    assert not retry.done()
    assert not read.done()
    release.set()
    await asyncio.wait_for(retry, 1)
    await read
    assert api._state.closed


async def test_direct_requests_enforce_owner_scope_and_nonempty_public_identity(api_server):
    api, state = await api_server()
    for path in api.owner_paths:
        with pytest.raises(ConfigError):
            await api.request("GET", path)
    for identity in ("", "   ", None, True):
        with pytest.raises(ConfigError):
            await api.request("GET", "/api/v1/game/player/binding", params={"uid": identity})
    assert state["grants"] == 0
