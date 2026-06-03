"""Thin Gemini client wrapper — the ONLY module that talks to the LLM API.

Reuses the existing pipeline's Gemini idiom (CLAUDE.md §9, §15); do NOT add
a provider abstraction (OpenRouter etc.) this phase — we are standardized
on Gemini, and the only call is name analysis.

Will provide:
  - client construction from GOOGLE_GENAI_API_KEY (env / .env).
  - a structured-output helper: prompt + pydantic model -> validated
    instance, using the existing extraction idiom
    (reference: product-scraping/src/scraper/extraction/stages/extract.py):
        GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=Model.model_json_schema(),
        )
        -> Model.model_validate_json(response.text)
  - generous max_output_tokens (~2000): gemini-2.5+/3 models burn output
    tokens on internal thinking and will otherwise truncate the JSON.

OPEN QUESTION (§9): model id — plan cites gemini-2.5-flash, the live
extraction code uses gemini-3-flash-preview. Confirm before implementing;
keep the model id a single constant here either way.

Boundary note: this wrapper performs network I/O, so callers in core/ take
the client as an injected argument — core functions stay pure/testable with
a mocked client (see tests/).
"""
