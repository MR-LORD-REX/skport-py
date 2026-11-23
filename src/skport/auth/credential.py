from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class Credential:
    """Account credential and signing key retained by an API instance.

    account_uid identifies the publisher account, not an in-game role.
    Credentials are locale-neutral and contain no game-specific bindings.
    """

    token: str = field(repr=False)
    cred: str = field(repr=False)
    salt: str = field(repr=False)
    user_id: str = ""
    account_uid: str = ""
    created_at: float = field(default_factory=time.time)
    refreshed_at: float = field(default_factory=time.time)
    generation: int = 0
    _renewed_at: float = field(default_factory=time.monotonic, repr=False)

    def touch(self) -> None:
        """Record a renewal so concurrent failures can share its result."""
        self.refreshed_at = time.time()
        self._renewed_at = time.monotonic()
        self.generation += 1

    def refresh_due(self, interval: float | None) -> bool:
        """Whether a caller-configured renewal interval has elapsed."""
        return interval is not None and time.monotonic() - self._renewed_at >= interval

    def clear(self) -> None:
        """Remove retained credential strings when the owning API closes."""
        self.token = self.cred = self.salt = ""
