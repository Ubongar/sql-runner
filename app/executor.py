"""
executor.py
Runs validated SQL against the DuckDB in-memory connection.
"""

import duckdb


def run_query(sql: str, conn: duckdb.DuckDBPyConnection) -> dict:
    """
    Returns {"success": bool, "result": [...] or None, "error": str or None}
    """
    try:
        result_df = conn.execute(sql).df()
        return {"success": True, "result": result_df.to_dict(orient="records"), "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}