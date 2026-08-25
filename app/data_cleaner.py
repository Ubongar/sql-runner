"""
data_cleaner.py
Cleans/preprocesses a DataFrame before it's loaded into DuckDB.
Tracks every cleaning action taken so it can be reported to the user.
"""

import re

import pandas as pd
import numpy as np

# Matches a column that IS "id" or ENDS in "_id" (e.g. employee_id, order_id),
# not just any column that merely contains the letters "id" somewhere
# (e.g. "avoid_list", "guidance", "valid_flag" no longer match).
ID_COLUMN_PATTERN = re.compile(r"(^id$)|(_id$)", re.IGNORECASE)


def clean_data(df: pd.DataFrame):
    """
    Returns (cleaned_df, report) where report is a list of dicts describing
    every cleaning action taken, e.g.:
      {"column": "salary", "issue": "missing values", "action": "filled with median", "count": 5}
    """
    df = df.copy()
    report = []

    # 1. Normalize column names (strip whitespace)
    original_cols = list(df.columns)
    df.columns = [c.strip() for c in df.columns]
    renamed = [(o, n) for o, n in zip(original_cols, df.columns) if o != n]
    for old, new in renamed:
        report.append({"column": new, "issue": "column name had whitespace", "action": f"renamed from '{old}'", "count": 1})

    # 2. Strip whitespace + normalize blank/nan-like strings in text columns
    for col in df.select_dtypes(include="object").columns:
        before = df[col].copy()
        df[col] = df[col].astype(str).str.strip()
        blank_like = df[col].isin(["nan", "None", "", "NaN", "null"])
        df[col] = df[col].mask(blank_like, None)
        changed = (before.astype(str).str.strip() != df[col].astype(str)).sum()
        if changed:
            report.append({"column": col, "issue": "whitespace/inconsistent blanks", "action": "trimmed and normalized", "count": int(changed)})

    # 3. Drop fully empty columns
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    if empty_cols:
        df = df.drop(columns=empty_cols)
        report.append({"column": empty_cols, "issue": "entirely empty column(s)", "action": "dropped", "count": len(empty_cols)})

    # 4. Drop fully empty rows
    before_rows = len(df)
    df = df.dropna(axis=0, how="all")
    if len(df) < before_rows:
        report.append({"column": None, "issue": "fully empty row(s)", "action": "dropped", "count": before_rows - len(df)})

    # 5. Drop exact duplicate rows
    before_rows = len(df)
    df = df.drop_duplicates()
    if len(df) < before_rows:
        report.append({"column": None, "issue": "exact duplicate rows", "action": "dropped, kept first", "count": before_rows - len(df)})

    # 6. Drop duplicates by likely ID column (real "id"/"*_id" match only, not substring)
    id_cols = [c for c in df.columns if ID_COLUMN_PATTERN.search(c)]
    if id_cols:
        before_rows = len(df)
        df = df.drop_duplicates(subset=id_cols[0], keep="first")
        if len(df) < before_rows:
            report.append({"column": id_cols[0], "issue": "duplicate ID rows", "action": "dropped, kept first", "count": before_rows - len(df)})

    # 7. Fill missing numeric values with column median
    for col in df.select_dtypes(include=[np.number]).columns:
        missing = df[col].isna().sum()
        if missing:
            df[col] = df[col].fillna(df[col].median())
            report.append({"column": col, "issue": "missing values", "action": "filled with column median", "count": int(missing)})

    # 8. Fill missing categorical/text values with "Unknown"
    for col in df.select_dtypes(include="object").columns:
        missing = df[col].isna().sum()
        if missing:
            df[col] = df[col].fillna("Unknown")
            report.append({"column": col, "issue": "missing values", "action": "filled with 'Unknown'", "count": int(missing)})

    return df.reset_index(drop=True), report