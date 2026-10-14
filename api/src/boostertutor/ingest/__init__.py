"""Pulling card data and statistics from upstream into Postgres.

Each source has a module whose parsing functions are pure (they take bytes,
file paths or dicts and return rows) and whose `load` does the I/O. Only
`fetching.py` touches the network.
"""
