"""Mock RecordSource: loads MaterialRecords from fixtures/*.json.

Implements ports/record_source.py. Parses the fixture file(s) into
core.models.MaterialRecord and yields them; validation errors in a fixture
should fail loudly (fixtures are ours — a bad one is a bug, not data noise).

The fixture shape mirrors the real persisted row (see fixtures/README.md)
so swapping in the Directus source later changes nothing downstream.
"""
