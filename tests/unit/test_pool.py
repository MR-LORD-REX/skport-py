import asyncio
from collections import Counter

import pytest

from skport.auth import Credential, TokenPool
from skport.config import ClientConfig
from skport.errors import APIError, AuthError, ConfigError, NetworkError, PoolExhausted


class FakeFlow:
    def __init__(self):
        self.calls = Counter()
        self.failed = set()
        self.refresh_error = None

    async def authenticate(self, token):
        self.calls[token] += 1
        await asyncio.sleep(0)
        if token in self.failed:
            raise AuthError("invalid account")
        return Credential(token, f"cred-{token}", f"salt-{token}")

    async def refresh(self, credential):
        self.calls["refresh"] += 1
        await asyncio.sleep(0)
        if self.refresh_error is not None:
            raise self.refresh_error
        credential.salt = "renewed"
        credential.touch()
        return credential


def make_pool(tokens=None, **settings):
    flow = FakeFlow()
    return TokenPool(tokens or ["a", "b", "c"], ClientConfig(**settings), flow), flow


@pytest.mark.asyncio
async def test_public_round_robin_reuses_credentials():
    pool, flow = make_pool()
    selected = []
    for _ in range(7):
        async with pool.lease() as unit:
            selected.append(unit.token)
    assert selected == ["a", "b", "c", "a", "b", "c", "a"]
    assert flow.calls == Counter({"a": 1, "b": 1, "c": 1})


@pytest.mark.asyncio
async def test_failed_cold_account_is_skipped_and_cooldown_is_respected():
    pool, flow = make_pool(["bad", "good"], cooldown=60)
    flow.failed.add("bad")
    async with pool.lease() as unit:
        assert unit.token == "good"
    async with pool.lease() as unit:
        assert unit.token == "good"
    assert flow.calls == Counter({"bad": 1, "good": 1})
    assert pool.units[0].failures == 1


@pytest.mark.asyncio
async def test_all_failed_accounts_remain_in_cooldown():
    pool, flow = make_pool(["bad"], cooldown=60)
    flow.failed.add("bad")
    for _ in range(2):
        with pytest.raises(PoolExhausted):
            async with pool.lease():
                pytest.fail("invalid account was leased")
    assert flow.calls["bad"] == 1


@pytest.mark.asyncio
async def test_cooldown_set_by_request_pipeline_survives_normal_lease_exit():
    pool, _ = make_pool(["a", "b"], cooldown=60)
    async with pool.lease() as first:
        first.cooldown(60)
    assert first.failures == 1
    assert not first.ready
    async with pool.lease() as second:
        assert second.token == "b"


@pytest.mark.asyncio
async def test_cold_network_failure_is_recorded_without_account_secrets():
    pool, flow = make_pool(["a"])

    async def unavailable(token):
        raise NetworkError("request did not complete")

    flow.authenticate = unavailable
    with pytest.raises(PoolExhausted) as failure:
        async with pool.lease():
            pytest.fail("unavailable account was leased")
    context = failure.value.context["accounts"]
    assert context[pool.units[0].fingerprint]["error"] == "NetworkError"


@pytest.mark.asyncio
async def test_warm_all_tolerates_one_failed_account():
    pool, flow = make_pool(["bad", "good"])
    flow.failed.add("bad")
    healthy = await pool.warm_all()
    assert [unit.token for unit in healthy] == ["good"]
    assert not pool.warm


@pytest.mark.asyncio
async def test_public_selection_prefers_free_unit():
    pool, _ = make_pool(["a", "b"])
    async with pool.lease(token="a"):
        async with pool.lease() as second:
            assert second.token == "b"


@pytest.mark.asyncio
async def test_owner_tokens_remain_outside_public_rotation():
    pool, flow = make_pool(["public"])
    first = await pool.credential_for("owner")
    assert await pool.credential_for("owner") is first
    for _ in range(3):
        async with pool.lease() as unit:
            assert unit.token == "public"
    assert len(pool) == 1
    assert flow.calls == Counter({"owner": 1, "public": 1})


@pytest.mark.asyncio
async def test_owner_business_failure_does_not_cool_down_valid_account():
    pool, _ = make_pool(["public"])
    with pytest.raises(APIError):
        async with pool.lease(token="owner"):
            raise APIError("business operation rejected")
    unit = pool.unit_for("owner")
    assert unit.ready
    assert unit.failures == 0


@pytest.mark.asyncio
async def test_account_gate_covers_credential_lookup_and_warming():
    pool, flow = make_pool(["a"])
    async with pool.lease(token="a"):
        lookup = asyncio.create_task(pool.credential_for("a"))
        warming = asyncio.create_task(pool.warm_all())
        await asyncio.sleep(0)
        assert not lookup.done()
        assert not warming.done()
        assert flow.calls["a"] == 1
    await asyncio.wait_for(asyncio.gather(lookup, warming), timeout=1)
    assert flow.calls["a"] == 1


@pytest.mark.asyncio
async def test_configured_account_concurrency_is_honored():
    pool, _ = make_pool(["a"], per_token_concurrency=2)
    async with pool.lease(token="a"):

        async def second():
            async with pool.lease(token="a") as unit:
                return unit.token

        assert await asyncio.wait_for(second(), timeout=1) == "a"


@pytest.mark.asyncio
async def test_default_gate_serializes_data_requests():
    pool, _ = make_pool(["a"])
    entered = asyncio.Event()

    async def second():
        async with pool.lease(token="a"):
            entered.set()

    async with pool.lease(token="a"):
        pending = asyncio.create_task(second())
        await asyncio.sleep(0)
        assert not entered.is_set()
    await asyncio.wait_for(pending, timeout=1)
    assert entered.is_set()


@pytest.mark.asyncio
async def test_concurrent_public_requests_obey_account_gates_without_starvation():
    pool, flow = make_pool()
    active = Counter()
    completed = Counter()
    maximum = Counter()
    peak_total = 0

    async def request():
        nonlocal peak_total
        async with pool.lease() as unit:
            active[unit.token] += 1
            maximum[unit.token] = max(maximum[unit.token], active[unit.token])
            peak_total = max(peak_total, sum(active.values()))
            await asyncio.sleep(0)
            active[unit.token] -= 1
            completed[unit.token] += 1

    await asyncio.wait_for(asyncio.gather(*(request() for _ in range(60))), timeout=1)
    assert completed == Counter({"a": 20, "b": 20, "c": 20})
    assert maximum == Counter({"a": 1, "b": 1, "c": 1})
    assert peak_total == 3
    assert flow.calls == Counter({"a": 1, "b": 1, "c": 1})


@pytest.mark.asyncio
async def test_concurrent_cold_failures_recheck_cooldown_after_auth_lock():
    pool, flow = make_pool(["bad"], per_token_concurrency=2, cooldown=60)
    flow.failed.add("bad")

    async def request():
        with pytest.raises(PoolExhausted):
            async with pool.lease():
                pytest.fail("invalid account was leased")

    await asyncio.wait_for(asyncio.gather(request(), request()), timeout=1)
    assert flow.calls["bad"] == 1
    assert pool.units[0].failures == 1
    assert pool.units[0].last_error == "AuthError"


@pytest.mark.asyncio
async def test_exclusions_accept_fingerprint_without_rotating_owner_accounts():
    pool, _ = make_pool(["a", "b"])
    async with pool.lease(exclude={pool.units[0].fingerprint}) as unit:
        assert unit.token == "b"


@pytest.mark.asyncio
async def test_renewal_generation_coalesces_concurrent_failures():
    pool, flow = make_pool(["a"])
    async with pool.lease(token="a") as unit:
        generation = unit.credential.generation
        results = await asyncio.gather(
            pool.renew(unit, generation), pool.renew(unit, generation), pool.renew(unit, generation)
        )
        assert all(result is unit.credential for result in results)
        assert unit.credential.generation == generation + 1
    assert flow.calls["refresh"] == 1
    assert flow.calls["a"] == 1


@pytest.mark.asyncio
async def test_refresh_rejection_exchanges_same_account_and_clears_old_strings():
    pool, flow = make_pool(["a"])
    flow.refresh_error = AuthError("credential expired")
    async with pool.lease(token="a") as unit:
        previous = unit.credential
        current = await pool.renew(unit, previous.generation)
        assert current is not previous
        assert current.generation == 1
        assert current.token == "a"
        assert previous.token == previous.cred == previous.salt == ""
    assert flow.calls == Counter({"a": 2, "refresh": 1})


@pytest.mark.asyncio
async def test_refresh_network_failure_preserves_credential_and_skips_full_login():
    pool, flow = make_pool(["a"])
    flow.refresh_error = NetworkError("temporary failure")
    async with pool.lease(token="a") as unit:
        previous = unit.credential
        with pytest.raises(NetworkError):
            await pool.renew(unit, previous.generation)
        assert unit.credential is previous
        assert previous.salt == "salt-a"
        assert unit.failures == 0
    assert flow.calls["a"] == 1


@pytest.mark.asyncio
async def test_optional_proactive_refresh_uses_one_request():
    pool, flow = make_pool(["a"], refresh_interval=0.1)
    credential = await pool.credential_for("a")
    credential._renewed_at -= 1
    async with pool.lease(token="a") as unit:
        assert unit.credential.salt == "renewed"
    assert flow.calls == Counter({"a": 1, "refresh": 1})


@pytest.mark.asyncio
async def test_cancelled_cold_login_does_not_poison_account():
    pool, flow = make_pool(["a"])
    entered = asyncio.Event()

    async def authenticate(token):
        entered.set()
        await asyncio.Event().wait()

    flow.authenticate = authenticate
    pending = asyncio.create_task(pool.credential_for("a"))
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not pool.units[0].gate.locked()
    assert pool.units[0].credential is None
    assert pool.units[0].failures == 0
    assert pool.units[0].cooldown_until == 0


@pytest.mark.asyncio
async def test_cancelled_warm_preserves_cancellation():
    pool, flow = make_pool(["a"])
    entered = asyncio.Event()

    async def authenticate(token):
        entered.set()
        await asyncio.Event().wait()

    flow.authenticate = authenticate
    pending = asyncio.create_task(pool.warm_all())
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert pool.units[0].failures == 0
    assert not pool.units[0].gate.locked()


@pytest.mark.asyncio
async def test_close_waits_for_lease_and_drops_retained_secrets():
    pool, _ = make_pool(["a"])
    async with pool.lease(token="a") as unit:
        credential = unit.credential
        closing = asyncio.create_task(pool.close())
        await asyncio.sleep(0)
        assert not closing.done()
        with pytest.raises(ConfigError):
            pool.unit_for("b")
    await asyncio.wait_for(closing, timeout=1)
    assert credential.token == credential.cred == credential.salt == ""
    assert unit.token == ""
    assert len(pool) == 0
    await pool.close()


def test_credential_and_unit_repr_exclude_secrets():
    pool, _ = make_pool(["secret-account-token"])
    credential = Credential("secret-account-token", "secret-cred", "secret-salt")
    pool.units[0].credential = credential
    assert "secret-" not in repr(credential)
    assert "secret-" not in repr(pool.units[0])


@pytest.mark.parametrize("tokens", [[], [""], ["  "], [None], [1]])
def test_invalid_tokens_raise_typed_configuration_errors(tokens):
    with pytest.raises(ConfigError):
        TokenPool(tokens, ClientConfig(), FakeFlow())


def test_duplicate_tokens_use_one_account_gate():
    pool, _ = make_pool(["a", " a ", "b", "a"])
    assert len(pool) == 2
    assert pool.unit_for("a") is pool.units[0]
