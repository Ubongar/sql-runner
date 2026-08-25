"""
ingest.py
Accepts a CSV or JSON file and loads it into a pandas DataFrame.
"""

import pandas as pd


def load_file(filepath: str) -> pd.DataFrame:
    lower = filepath.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(filepath)
    elif lower.endswith(".json"):
        return pd.read_json(filepath)
    else:
        raise ValueError("Unsupported file type. Use .csv or .json")