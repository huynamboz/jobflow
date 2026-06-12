"""LLM service module — Dependency Injection via Protocol.

Usage from any other module:
    from apps.llm.service import LLMService

    response = LLMService.complete([
        {"role": "user", "content": "Hello"}
    ])
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol (interface) — add new providers by implementing this
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClientProtocol(Protocol):
    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str: ...

    def test_connection(self) -> tuple[bool, str]: ...


# ---------------------------------------------------------------------------
# OpenAI-compatible implementation (works with OpenAI, Anthropic, Gemini, Ollama…)
# ---------------------------------------------------------------------------

class OpenAICompatibleClient:
    """Concrete LLM client for any OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
        **kwargs,
    ) -> str:
        # Use stream=True to support providers that only return SSE chunks
        create_kwargs = dict(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        if json_schema:
            # Native structured output → guaranteed valid JSON matching the schema.
            create_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "extract", "schema": json_schema},
            }
        stream = self._client.chat.completions.create(**create_kwargs)
        parts = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        return "".join(parts)

    def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ):
        """Yield content deltas as they arrive (token streaming)."""
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def test_connection(self) -> tuple[bool, str]:
        try:
            result = self.complete(
                [{"role": "user", "content": "Say OK"}],
                max_tokens=10,
            )
            return True, result.strip()
        except Exception as exc:
            return False, str(exc)


# ---------------------------------------------------------------------------
# Messages-endpoint client (Anthropic-style: POST /messages, SSE response)
# ---------------------------------------------------------------------------

class MessagesClient:
    """Client for providers that expose a /messages endpoint with SSE streaming."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        # Ensure base_url ends without slash; append /messages
        self._url = base_url.rstrip("/") + "/messages"

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
        **kwargs,
    ) -> str:
        import json as _json

        import httpx

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        if json_schema:
            # Forced tool-use → structured output (non-streaming): the model must
            # call the "extract" tool whose input matches the schema.
            payload = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": [{"name": "extract", "description": "Return the extracted fields.", "input_schema": json_schema}],
                "tool_choice": {"type": "tool", "name": "extract"},
            }
            resp = httpx.post(self._url, json=payload, headers=headers, timeout=httpx.Timeout(120.0, connect=10.0))
            resp.raise_for_status()
            for block in resp.json().get("content", []):
                if block.get("type") == "tool_use":
                    return _json.dumps(block.get("input") or {})
            return ""

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        parts = []
        with httpx.stream("POST", self._url, json=payload, headers=headers, timeout=httpx.Timeout(120.0, connect=10.0)) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = _json.loads(raw)
                    # Anthropic format: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
                    if chunk.get("type") == "content_block_delta":
                        parts.append(chunk.get("delta", {}).get("text") or "")
                    # OpenAI format: {"choices":[{"delta":{"content":"..."}}]}
                    elif chunk.get("choices"):
                        parts.append(chunk["choices"][0].get("delta", {}).get("content") or "")
                except _json.JSONDecodeError:
                    continue
        return "".join(parts)

    def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ):
        """Yield text deltas as they arrive (token streaming)."""
        import json as _json

        import httpx

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        with httpx.stream("POST", self._url, json=payload, headers=headers, timeout=httpx.Timeout(120.0, connect=10.0)) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = _json.loads(raw)
                    if chunk.get("type") == "content_block_delta":
                        yield chunk.get("delta", {}).get("text") or ""
                    elif chunk.get("choices"):
                        yield chunk["choices"][0].get("delta", {}).get("content") or ""
                except _json.JSONDecodeError:
                    continue

    def test_connection(self) -> tuple[bool, str]:
        try:
            result = self.complete(
                [{"role": "user", "content": "Say OK"}],
                max_tokens=10,
            )
            return True, result.strip() or "(empty)"
        except Exception as exc:
            return False, str(exc)


# ---------------------------------------------------------------------------
# Factory — maps provider records to concrete clients
# ---------------------------------------------------------------------------

def _build_client(provider) -> LLMClientProtocol:
    """Build the right client for a given LLMProvider instance."""
    if getattr(provider, "client_type", "openai") == "messages":
        return MessagesClient(
            api_key=provider.api_key,
            model=provider.model,
            base_url=provider.base_url,
        )
    return OpenAICompatibleClient(
        api_key=provider.api_key,
        model=provider.model,
        base_url=provider.base_url,
    )


# ---------------------------------------------------------------------------
# Logging helper — never raises so a DB/migration issue won't break LLM calls
# ---------------------------------------------------------------------------

def _safe_log(**kwargs) -> None:
    try:
        from apps.llm.models import LLMCallLog
        LLMCallLog.objects.create(**kwargs)
    except Exception as exc:
        logger.warning("Failed to write LLMCallLog: %s", exc)


# ---------------------------------------------------------------------------
# LLMService — the public facade other modules call
# ---------------------------------------------------------------------------

class LLMService:
    """Singleton-style facade. Other modules only import this class."""

    @staticmethod
    def get_active_provider():
        from apps.llm.models import LLMProvider
        provider = LLMProvider.objects.filter(is_active=True).first()
        if not provider:
            raise RuntimeError(
                "No active LLM provider configured. "
                "Go to /api/admin/llm/providers/ and activate one."
            )
        return provider

    @staticmethod
    def get_client() -> LLMClientProtocol:
        provider = LLMService.get_active_provider()
        return _build_client(provider)

    @staticmethod
    def complete(
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        feature: str = "",
        json_schema: dict | None = None,
        **kwargs,
    ) -> str:
        """Send messages to the active LLM provider, log the call, and return
        response text. Pass `json_schema` to request native structured output
        (OpenAI response_format / Anthropic forced tool-use); if the provider
        doesn't support it, automatically falls back to plain prompt-parse."""
        import time

        from apps.llm.models import LLMCallLog

        try:
            provider = LLMService.get_active_provider()
        except RuntimeError as exc:
            _safe_log(provider=None, feature=feature, status="error", error_message=str(exc))
            raise

        client = _build_client(provider)

        # Build input preview from last user message
        input_preview = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                input_preview = str(msg.get("content", ""))[:1000]
                break

        start = time.time()
        try:
            try:
                result = client.complete(messages, temperature=temperature, max_tokens=max_tokens,
                                         json_schema=json_schema, **kwargs)
            except Exception as exc:  # noqa: BLE001 — provider may not support structured output
                if not json_schema:
                    raise
                logger.warning("Structured output failed (%s) — falling back to prompt-parse", str(exc)[:150])
                result = client.complete(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
            duration_ms = int((time.time() - start) * 1000)
            _safe_log(
                provider=provider, feature=feature, status="success",
                input_preview=input_preview, output=result, duration_ms=duration_ms,
            )
            return result
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            _safe_log(
                provider=provider, feature=feature, status="error",
                input_preview=input_preview, error_message=str(exc)[:1000], duration_ms=duration_ms,
            )
            raise

    @staticmethod
    def stream(
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        feature: str = "",
        **kwargs,
    ):
        """Yield response text deltas from the active provider, logging once done."""
        import time

        provider = LLMService.get_active_provider()
        client = _build_client(provider)

        input_preview = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                input_preview = str(msg.get("content", ""))[:1000]
                break

        start = time.time()
        parts: list[str] = []
        try:
            for delta in client.stream(messages, temperature=temperature, max_tokens=max_tokens, **kwargs):
                parts.append(delta)
                yield delta
            _safe_log(
                provider=provider, feature=feature, status="success",
                input_preview=input_preview, output="".join(parts),
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as exc:
            _safe_log(
                provider=provider, feature=feature, status="error",
                input_preview=input_preview, error_message=str(exc)[:1000],
                duration_ms=int((time.time() - start) * 1000),
            )
            raise
