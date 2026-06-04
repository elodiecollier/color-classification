"""Demo webapp: search + mock admin view over the mock DB (visual demo only).

Deliberately minimal — NOT production search and NOT the real integration
path (that's ports/ + adapters/). One FastAPI app serving a JSON API plus a
static vanilla-JS frontend. Run with:

    uv run uvicorn webapp.main:app --reload
"""
