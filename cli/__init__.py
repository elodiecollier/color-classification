"""Entry points — the only place adapters get wired to ports (composition root).

  run_batch.py  classify every record from the record source -> file sink
  search.py     the thin search demo over the batch output

cli/ does composition and argument parsing only; all logic lives in core/.
"""
