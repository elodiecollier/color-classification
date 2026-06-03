"""The integration seam — interfaces ONLY, no implementations (CLAUDE.md §11).

Each port is an abstract interface (Protocol or ABC) that `core/` and `cli/`
program against. Implementations live in `adapters/`. Because every external
dependency sits behind one of these, integration later = writing
adapters/r2/* and adapters/directus/* against the SAME interfaces, with
core/ unchanged (§12).

Lock these signatures early — they're contracts for the parallel
workstreams (§14), alongside the §8 schema in core/models.py.

Ports:
  record_source.py  read the already-persisted records to batch over
  image_store.py    read swatch image bytes by reference (R2 key / path)
  color_sink.py     write color records + the review queue
  clustering.py     the swappable pixel-clustering algorithm
"""
