"""Authentication and human-interaction ports."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from media_sync.domain import AccountRef, AuthChallenge, AuthResult, AuthStatus, CapabilitySet


@runtime_checkable
class InteractionPort(Protocol):
    """A UI-independent boundary for an interactive login challenge."""

    async def request(self, challenge: AuthChallenge) -> str | None:
        """Present a challenge and return an opaque response or cancellation."""
        ...


@runtime_checkable
class AuthPort(Protocol):
    """Authenticate an account without exposing credential values."""

    @property
    def name(self) -> str:
        """Return the stable adapter implementation name."""
        ...

    def capabilities(self) -> CapabilitySet:
        """Return qualified capabilities for this adapter instance."""
        ...

    async def auth_status(self, account: AccountRef) -> AuthStatus:
        """Return the current observable session state."""
        ...

    async def ensure_session(
        self,
        account: AccountRef,
        interaction: InteractionPort | None = None,
    ) -> AuthResult:
        """Ensure an authenticated session or return an actionable state."""
        ...


__all__ = ["AuthPort", "InteractionPort"]
