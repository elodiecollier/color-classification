"""Mock ImageStore: reads swatch images from local files.

Implements ports/image_store.py. The record's image reference is a path
relative to fixtures/images/ (where the real adapter would treat it as an
R2 object key). Missing file -> None (a normal §6 branch, not an error).
"""
