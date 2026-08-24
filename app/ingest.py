"""
ingest.py
Accepts a CSV or JSON file and loads it into a pandas DataFrame.
"""

import pandas as pd


def load_file(filepath: str) -> pd.DataFrame:
    if filepath.endswith(".csv"):
        return pd.read_csv(filepath)
    elif filepath.endswith(".json"):
        return pd.read_json(filepath)
    else:
        raise ValueError("Unsupported file type. Use .csv or .json")