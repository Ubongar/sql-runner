"""
db_loader.py
Registers the DataFrame as a DuckDB table (in-memory, no server needed).
"""

import duckdb
import pandas as pd


def load_data(df: pd.DataFrame, table_name: str, conn: duckdb.DuckDBPyConnection):
    conn.register(table_name, df)