"""LLM adapters — concrete `ports.llm.LLMClient` implementations.

The SDK-touching code lives here, never in `core/`. `openrouter.py` is the one
we use (OpenRouter gateway → Gemini flash).
"""
