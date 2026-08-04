"""Provider interface for optional local language models.

FORGE treats language models as an accessory, never as a dependency:

* every operation has a deterministic fallback that runs with no provider,
* nothing generated is written to a user-visible field without an explicit
  "accept" step,
* every generated object records the provider, model and prompt in the
  ``generation`` table so it can be audited or reverted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    name: str
    available: bool
    detail: str
    models: tuple[str, ...] = ()
    base_url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "detail": self.detail,
            "models": list(self.models),
            "base_url": self.base_url,
        }


@dataclass(slots=True)
class LLMResult:
    text: str
    model: str
    provider: str
    duration_ms: int
    prompt: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMUnavailable(RuntimeError):
    """Raised when a provider is disabled, unreachable or misconfigured."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def status(self) -> ProviderStatus: ...

    def complete(self, prompt: str, *, system: str | None = None, model: str | None = None,
                 temperature: float = 0.2, max_tokens: int | None = None) -> LLMResult: ...

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...


class NullProvider:
    """Always-unavailable provider used when local intelligence is disabled."""

    name = "none"

    def __init__(self, detail: str = "Local LLM features are disabled in Settings.") -> None:
        self._detail = detail

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, False, self._detail)

    def complete(self, prompt: str, **_: Any) -> LLMResult:
        raise LLMUnavailable(self._detail)

    def embed(self, texts: list[str], **_: Any) -> list[list[float]]:
        raise LLMUnavailable(self._detail)
