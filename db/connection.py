"""
db/connection.py
Provides a shared in-memory DuckDB connection. No server or credentials needed.
"""

import duckdb


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database=":memory:")