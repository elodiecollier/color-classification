"""Port: the text LLM used for swatch-NAME analysis (CLAUDE.md §9).

A minimal chat interface so `core/name_analysis.py` can build prompts and parse
responses WITHOUT importing any SDK. Implemented by `adapters/llm/openrouter.py`
(OpenRouter gateway → Gemini flash); tests inject a fake.
"""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Structural interface for a JSON-returning chat completion."""

    def complete_json(self, *, system: str, user: str) -> str:
        """Run one completion and return the raw response text.

        The caller asks the model for a JSON object; this returns the model's
        text verbatim (possibly malformed) — `core/name_analysis` validates it
        defensively (§9). Implementations may raise on transport/auth errors.
        """
        ...
