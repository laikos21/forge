"""Optional local intelligence: provider resolution."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...config import get_settings
from .. import settings_store
from .base import LLMProvider, LLMResult, LLMUnavailable, NullProvider, ProviderStatus
from .ollama import OllamaProvider

__all__ = [
    "LLMProvider",
    "LLMResult",
    "LLMUnavailable",
    "NullProvider",
    "OllamaProvider",
    "ProviderStatus",
    "provider_for",
    "provider_status",
]


def provider_for(session: Session, *, force: bool = False) -> LLMProvider | None:
    """Return the configured provider, or ``None`` when disabled.

    ``force=True`` builds the provider even when the feature flag is off, which
    the Settings screen uses to test connectivity before enabling it.
    """

    preferences = settings_store.get_all(session)
    if not preferences["llm.enabled"] and not force:
        return None
    if preferences["llm.provider"] != "ollama":
        return None
    return OllamaProvider(
        base_url=preferences["llm.base_url"] or get_settings().ollama_base_url,
        model=preferences["llm.model"],
        embed_model=preferences["semantic.model"],
        timeout=get_settings().llm_timeout_seconds,
    )


def provider_status(session: Session, *, probe: bool = False) -> ProviderStatus:
    """Describe the configured provider.

    When the feature is disabled this answers *without touching the network*.
    Probing a closed port costs seconds on Windows (the IPv6 attempt for
    ``localhost`` has to time out first), and no screen should pay that just to
    render "disabled". Pass ``probe=True`` for the explicit "test connection"
    action.
    """

    preferences = settings_store.get_all(session)
    enabled = bool(preferences["llm.enabled"])

    if not enabled and not probe:
        return ProviderStatus(
            preferences["llm.provider"],
            False,
            "Local LLM features are turned off in Settings. "
            "Enable them, or use Re-check to test the connection now.",
            (),
            preferences["llm.base_url"],
        )

    provider = provider_for(session, force=True)
    if provider is None:
        return NullProvider("No local provider is configured.").status()

    status = provider.status()
    if not enabled:
        return ProviderStatus(
            status.name,
            False,
            f"Local LLM features are turned off in Settings. {status.detail}",
            status.models,
            status.base_url,
        )
    return status
