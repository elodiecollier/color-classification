"""OpenRouter LLM adapter (OpenAI-compatible) — implements `ports.llm.LLMClient`.

Routes to Gemini flash THROUGH OpenRouter, so we keep "Gemini for language"
(CLAUDE.md §3, §9) while using the `OPENROUTER_API_KEY` we actually have.
OpenRouter is an OpenAI-compatible gateway, so we use the `openai` SDK pointed at
its base URL. The SDK lives HERE, never in `core/` — `core/name_analysis` takes
this as an injected client and stays import-clean + testable with a fake.
"""

from __future__ import annotations

import base64
import os

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash"


class OpenRouterClient:
    """`ports.llm.LLMClient` backed by OpenRouter's OpenAI-compatible API."""

    def __init__(self, *, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self._client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def complete_json(self, *, system: str, user: str) -> str:
        """One completion, JSON-object mode, deterministic (temperature 0)."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return response.choices[0].message.content or ""

    def complete_json_vision(
        self, *, system: str, user: str, image_bytes: bytes, mime_type: str
    ) -> str:
        """`ports.llm.VisionLLMClient`: one multimodal completion, JSON-object
        mode. The image rides along as an OpenAI-style base64 data URL (the
        format OpenRouter forwards to Gemini)."""
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return response.choices[0].message.content or ""
