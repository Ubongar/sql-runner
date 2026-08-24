"""
schema_infer.py
Detects column names/types from a DataFrame and maps them to MySQL types.
"""

import pandas as pd

TYPE_MAP = {
    "int64": "INT",
    "float64": "DECIMAL(12,2)",
    "bool": "BOOLEAN",
    "datetime64[ns]": "DATETIME",
    "object": "VARCHAR(255)",
}


def infer_schema(df: pd.DataFrame) -> dict:
    columns = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        # try to catch date-like object columns
        if dtype == "object":
            try:
                pd.to_datetime(df[col], errors="raise")
                dtype = "datetime64[ns]"
            except Exception:
                pass
        mysql_type = TYPE_MAP.get(dtype, "VARCHAR(255)")
        columns.append({"name": col, "type": mysql_type})
    return {"columns": columns}