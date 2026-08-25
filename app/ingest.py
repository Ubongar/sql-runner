"""
ingest.py
Accepts a CSV or JSON file and loads it into a pandas DataFrame.
"""

import pandas as pd
import csv
import json
from pathlib import Path


def load_file(filepath: str) -> pd.DataFrame:
    if filepath.endswith(".csv"):
        return pd.read_csv(filepath)
    elif filepath.endswith(".json"):
        return pd.read_json(filepath)
    else:
        raise ValueError("Unsupported file type. Use .csv or .json")
    
def _infer_type(value):
    """Infer a simple type name for a single scalar value."""
    if value is None or value == "":
        return None
    for t in (int, float):
        try:
            t(value)
            return t.__name__
        except (ValueError, TypeError):
            continue
    return "str"
 
 
def _column_dtype(values):
    """Infer a single dtype for a whole column, falling back to 'str' on mixed types."""
    non_empty = [v for v in values if v not in (None, "")]
    if not non_empty:
        return "str"
    dtype = _infer_type(non_empty[0])
    for v in non_empty:
        if _infer_type(v) != dtype:
            return "str"
    return dtype
 
 
def parse_file(path):
    """
    Parse a .csv or .json file into a list of {(header, dtype): [column_values]} dicts.
 
    - CSV: read via the csv module, all values kept as raw strings.
    - JSON: expects a list of flat objects (list of dicts); missing keys
      in a given row become None.
    """
    path = Path(path)
    suffix = path.suffix.lower()
 
    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
            columns = {h: [] for h in headers}
            for row in reader:
                for h, val in zip(headers, row):
                    columns[h].append(val)
 
    elif suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("JSON file must contain a list of objects")
        headers = list(data[0].keys()) if data else []
        columns = {h: [row.get(h) for row in data] for h in headers}
 
    else:
        raise ValueError(f"Unsupported file type: {suffix!r} (expected .csv or .json)")
 
    result = []
    for h in headers:
        values = columns[h]
        dtype = _column_dtype(values)
        result.append({(h, dtype): values})
 
    return result

