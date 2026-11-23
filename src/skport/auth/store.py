from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

from skport.auth.credential import Credential
from skport.errors import ConfigError


class CredentialStore:
    """Optional disk cache; the default token pool keeps credentials in RAM.

    Entries contain credentials and signing keys, never account tokens. Their
    filenames include a deployment namespace to prevent cross-region reuse.
    """

    def __init__(self, root: str | Path, *, namespace: str = "global") -> None:
        self.root = Path(root).expanduser()
        self.namespace = namespace

    def _path(self, token: str) -> Path:
        digest = hashlib.sha256(f"{self.namespace}\0{token}".encode()).hexdigest()
        return self.root / f"{digest}.json"

    def load(self, token: str) -> Credential | None:
        """Load a valid cache entry, treating missing or corrupt files as misses."""
        try:
            data = json.loads(self._path(token).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != 1:
                return None
            cred, salt = data.get("cred"), data.get("salt")
            if not isinstance(cred, str) or not cred or not isinstance(salt, str) or not salt:
                return None
            created = float(data["created_at"])
            refreshed = float(data["refreshed_at"])
            generation = int(data.get("generation", 0))
            if (
                not all(math.isfinite(value) and value > 0 for value in (created, refreshed))
                or generation < 0
            ):
                return None
            credential = Credential(
                token=token,
                cred=cred,
                salt=salt,
                user_id=str(data.get("user_id") or ""),
                account_uid=str(data.get("account_uid") or ""),
                created_at=created,
                refreshed_at=refreshed,
                generation=generation,
            )
            credential._renewed_at -= max(0.0, time.time() - refreshed)
            return credential
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def save(self, credential: Credential) -> None:
        """Atomically write an entry without serializing the account token."""
        payload = {
            "schema": 1,
            "cred": credential.cred,
            "salt": credential.salt,
            "user_id": credential.user_id,
            "account_uid": credential.account_uid,
            "created_at": credential.created_at,
            "refreshed_at": credential.refreshed_at,
            "generation": credential.generation,
        }
        temporary: str | None = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=self.root, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
            os.replace(temporary, self._path(credential.token))
            temporary = None
        except (OSError, ValueError) as exc:
            raise ConfigError("credential cache could not be written") from exc
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def clear(self, token: str) -> None:
        """Remove one entry; a missing file is already cleared."""
        self._path(token).unlink(missing_ok=True)
