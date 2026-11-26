import json

import pytest

from skport.auth import Credential, CredentialStore


def test_store_round_trip_excludes_account_token(tmp_path):
    store = CredentialStore(tmp_path)
    credential = Credential("private-account-token", "stored-cred", "stored-salt", account_uid="account-uid")
    credential.touch()
    store.save(credential)
    entries = list(tmp_path.glob("*.json"))
    assert len(entries) == 1
    assert "private-account-token" not in entries[0].name
    assert "private-account-token" not in entries[0].read_text()
    loaded = store.load(credential.token)
    assert loaded.cred == credential.cred
    assert loaded.salt == credential.salt
    assert loaded.account_uid == "account-uid"
    assert loaded.generation == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_store_namespaces_separate_deployments(tmp_path):
    global_store = CredentialStore(tmp_path, namespace="global")
    other_store = CredentialStore(tmp_path, namespace="other")
    global_store.save(Credential("account-token", "cred", "salt"))
    assert other_store.load("account-token") is None


@pytest.mark.parametrize("content", ["invalid-json", "[]", "null", "{}", '{"schema": 1, "cred": []}'])
def test_store_corrupt_entry_is_cache_miss(tmp_path, content):
    store = CredentialStore(tmp_path)
    store._path("token").write_text(content)
    assert store.load("token") is None


def test_store_invalid_timestamp_is_cache_miss(tmp_path):
    store = CredentialStore(tmp_path)
    credential = Credential("token", "cred", "salt")
    store.save(credential)
    path = store._path("token")
    body = json.loads(path.read_text())
    body["refreshed_at"] = float("inf")
    path.write_text(json.dumps(body))
    assert store.load("token") is None


def test_store_clear_is_idempotent(tmp_path):
    store = CredentialStore(tmp_path)
    store.save(Credential("token", "cred", "salt"))
    store.clear("token")
    store.clear("token")
    assert store.load("token") is None
