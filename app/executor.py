"""
executor.py
Runs validated SQL against the DuckDB in-memory connection.
Now supports executing multiple SQL statements, returning grouped results.
"""

import duckdb
import sqlglot


def run_query(sql: str, conn: duckdb.DuckDBPyConnection) -> dict:
    """
    Returns {"success": bool, "result": [...] or {...}, "error": str or None}
    """
    try:
        # Safely extract individual queries from the SQL string
        statements = [expr.sql(dialect="duckdb") for expr in sqlglot.parse(sql, dialect="duckdb") if expr]
        
        all_results = []
        for stmt in statements:
            result_df = conn.execute(stmt).df()
            all_results.append(result_df.to_dict(orient="records"))
        
        # If only one query was run, return the flat list (backward compatibility)
        if len(all_results) == 1:
            final_result = all_results[0]
        else:
            # If multiple queries, group them nicely in a dictionary
            final_result = {f"query_{i+1}": res for i, res in enumerate(all_results)}

        return {"success": True, "result": final_result, "error": None}
    
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}