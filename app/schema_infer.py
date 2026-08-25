"""
schema_infer.py
Detects column names/types from a DataFrame and maps them to SQL types
(used for DuckDB and described to the language model - not MySQL).
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

        if dtype == "object":
            # data_cleaner.py fills missing text with the literal "Unknown".
            # If we tested the whole column for date-ness, one "Unknown" would
            # fail the whole column and mislabel a real date column as text.
            # So we test only the real (non-placeholder) values instead.
            real_values = df[col][df[col] != "Unknown"].dropna()
            if len(real_values) > 0:
                parsed = pd.to_datetime(real_values, errors="coerce")
                if parsed.notna().all():
                    dtype = "datetime64[ns]"

        sql_type = TYPE_MAP.get(dtype, "VARCHAR(255)")
        columns.append({"name": col, "type": sql_type})
    return {"columns": columns}