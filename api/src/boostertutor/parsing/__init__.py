"""Turning each draft input format into the canonical `DraftLog`.

Pure, like `analysis/`: no network, no database, no clock. A parser is
handed the raw input and a name index (built from the database by its
caller), so every test runs against saved payloads.
"""
