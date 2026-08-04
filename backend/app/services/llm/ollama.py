"""Ollama provider (optional, local-only).

Talks to ``http://localhost:11434`` over plain HTTP. Nothing leaves the machine
and no key is involved. Every failure mode is converted into
:class:`LLMUnavailable` with a message the Settings screen can display verbatim.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .base import LLMResult, LLMUnavailable, ProviderStatus


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3.1:8b",
                 embed_model: str = "nomic-embed-text", timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.timeout = timeout

    # -- introspection ------------------------------------------------------

    #: Probe timeout. A local provider either answers immediately or is absent;
    #: a long timeout would only make screens wait for a connection refusal.
    PROBE_TIMEOUT = 2.0

    def list_models(self) -> list[str]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=self.PROBE_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
        payload = response.json()
        return sorted(str(m.get("name", "")) for m in payload.get("models", []) if m.get("name"))

    def status(self) -> ProviderStatus:
        try:
            models = self.list_models()
        except LLMUnavailable as exc:
            return ProviderStatus(self.name, False, str(exc), base_url=self.base_url)
        if not models:
            return ProviderStatus(
                self.name,
                False,
                f"Ollama is running at {self.base_url} but no models are installed. "
                f"Run: ollama pull {self.model}",
                base_url=self.base_url,
            )
        detail = f"Connected to Ollama at {self.base_url}."
        if self.model not in models:
            detail += f" Model '{self.model}' is not installed; run: ollama pull {self.model}"
        return ProviderStatus(self.name, True, detail, tuple(models), self.base_url)

    # -- generation ---------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        started = time.perf_counter()
        try:
            response = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise LLMUnavailable(f"Ollama returned {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Could not reach Ollama at {self.base_url}: {exc}") from exc

        data = response.json()
        return LLMResult(
            text=str(data.get("response", "")).strip(),
            model=payload["model"],
            provider=self.name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            prompt=prompt,
            raw={k: v for k, v in data.items() if k != "response"},
        )

    # -- embeddings ---------------------------------------------------------

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        model = model or self.embed_model
        vectors: list[list[float]] = []
        for text in texts:
            try:
                response = httpx.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMUnavailable(
                    f"Ollama embedding request failed ({exc.response.status_code}). "
                    f"Is '{model}' pulled? Run: ollama pull {model}"
                ) from exc
            except httpx.HTTPError as exc:
                raise LLMUnavailable(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
            vector = response.json().get("embedding")
            if not isinstance(vector, list) or not vector:
                raise LLMUnavailable(f"Ollama returned no embedding for model '{model}'.")
            vectors.append([float(v) for v in vector])
        return vectors
