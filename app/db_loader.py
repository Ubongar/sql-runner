"""
db_loader.py
Registers a DataFrame as a DuckDB table (in-memory, no server needed).
Now supports multiple tables per run (one per input file).
"""

import re

import duckdb
import pandas as pd


def sanitize_table_name(name: str) -> str:
    """
    Turns a filename like 'sample2 sales.csv' into a safe SQL table
    identifier like 'sample2_sales'. Prevents odd filenames from producing
    invalid or unsafe table names.
    """
    name = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if not name or name[0].isdigit():
        name = f"t_{name}"
    return name.lower()


def load_data(df: pd.DataFrame, table_name: str, conn: duckdb.DuckDBPyConnection):
    conn.register(table_name, df)