"""
schema_infer.py
Detects column names/types from a DataFrame and maps them to SQL types
(used for DuckDB and described to the language model - not MySQL).
"""

import pandas as pd
import base64
import binascii


TYPE_MAP = {
    "int64": "INT",
    "float64": "DECIMAL(12,2)",
    "bool": "BOOLEAN",
    "datetime64[ns]": "DATETIME",
    "object": "NVARCHAR(255)",
    "image": "BLOB",
}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff")

# Magic bytes for common image formats, used to verify base64-decoded content
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"BM": "bmp",
    b"RIFF": "webp",  # WEBP starts with RIFF....WEBP
}


def _is_image_path(value) -> bool:
    return isinstance(value, str) and value.lower().split("?")[0].endswith(IMAGE_EXTENSIONS)


def _is_base64_image(value) -> bool:
    if not isinstance(value, str):
        return False

    s = value.strip()

    # Handle data URIs like "data:image/png;base64,iVBOR..."
    if s.startswith("data:image/"):
        s = s.split(",", 1)[-1]

    # Cheap pre-filter: base64 image strings are typically long
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