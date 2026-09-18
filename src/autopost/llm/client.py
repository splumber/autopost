"""Thin OpenAI-compatible chat client pointed at the user's local model proxy/Ollama."""
from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from autopost.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client = httpx.AsyncClient(
            base_url=cfg.base_url,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            timeout=cfg.request_timeout_sec,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, system: str, user: str, temperature: float | None = None) -> str:
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
            "stream": True,
        }
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                return await self._stream_chat(payload)
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_err = exc
                logger.warning("LLM call failed (attempt %s/%s): %s", attempt, self.cfg.max_retries, exc)
                await asyncio.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"LLM call failed after {self.cfg.max_retries} attempts") from last_err

    async def _stream_chat(self, payload: dict) -> str:
        """The proxy always responds as SSE (`data: {...}` chunks) regardless of the
        `stream` flag, so we parse it as a stream rather than a single JSON body."""
        chunks: list[str] = []
        async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                event = json.loads(data_str)
                delta = event.get("choices", [{}])[0].get("delta", {})
                if content := delta.get("content"):
                    chunks.append(content)
        if not chunks:
            raise ValueError("Empty streamed response from LLM proxy")
        return "".join(chunks)

    async def chat_json(self, system: str, user: str, temperature: float | None = None) -> dict:
        """Ask for JSON and parse it defensively -- local models don't always
        respect strict JSON-only instructions, so we extract the first {...} block."""
        raw = await self.chat(
            system + "\n\nRespond with ONLY valid JSON, no markdown fences, no commentary.",
            user,
            temperature,
        )
        return _extract_json(raw)


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse JSON from LLM response: {text[:300]!r}")
