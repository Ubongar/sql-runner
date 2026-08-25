"""
schema_infer.py
Detects column names/types from a DataFrame and maps them to SQL types.
Now dynamically injects min/max bounds and data samples for the AI Query Rewriter.
"""

import base64
import binascii
from typing import Any

import pandas as pd

TYPE_MAP = {
    "int64": "INT",
    "float64": "DECIMAL(12,2)",
    "bool": "BOOLEAN",
    "datetime64[ns]": "DATETIME",
    "object": "VARCHAR(255)",
    "image": "BLOB",
}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff")

IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"BM": "bmp",
    b"RIFF": "webp",
}

def _is_image_path(value) -> bool:
    return isinstance(value, str) and value.lower().split("?")[0].endswith(IMAGE_EXTENSIONS)

def _is_base64_image(value) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if s.startswith("data:image/"):
        s = s.split(",", 1)[-1]
    if len(s) < 20:
        return False
    try:
        decoded = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        return False
    return any(decoded.startswith(sig) for sig in IMAGE_SIGNATURES)

def _is_image_value(value) -> bool:
    return _is_image_path(value) or _is_base64_image(value)

def _column_looks_like_images(series: pd.Series, sample_size: int = 20, threshold: float = 0.8) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return False
    sample = non_null.head(sample_size)
    matches = sum(_is_image_value(v) for v in sample)
    return (matches / len(sample)) >= threshold

def infer_schema(df: pd.DataFrame) -> dict:
    columns = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        samples = []
        stats = {}

        if dtype == "object":
            if _column_looks_like_images(df[col]):
                dtype = "image"
            else:
                real_values = df[col][df[col] != "Unknown"].dropna()
                if len(real_values) > 0:
                    parsed = pd.to_datetime(real_values, errors="coerce")
                    if parsed.notna().all():
                        dtype = "datetime64[ns]"
                        stats["min"] = parsed.min().strftime('%Y-%m-%d')
                        stats["max"] = parsed.max().strftime('%Y-%m-%d')
                    else:
                        samples = real_values.unique()[:3].tolist()
                        
        elif dtype in ("int64", "float64"):
            real_values = df[col].dropna()
            if len(real_values) > 0:
                stats["min"] = float(real_values.min())
                stats["max"] = float(real_values.max())

        sql_type = TYPE_MAP.get(dtype, "VARCHAR(255)")
        
        # FIX: Explicitly tell Pylance this dict holds mixed types
        col_def: dict[str, Any] = {"name": col, "type": sql_type}
        
        if samples:
            col_def["samples"] = samples
        if stats:
            col_def["stats"] = stats
            
        columns.append(col_def)
        
    return {"columns": columns}