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

# Heuristic for "this text column is a category/status flag, not free text or
# a name": low absolute number of distinct values, and those values repeat
# a lot relative to row count. Names/descriptions are near-unique per row and
# won't qualify, so their casing is left untouched.
MAX_CATEGORY_UNIQUES = 20
MAX_CATEGORY_UNIQUE_RATIO = 0.5


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

    # 3. Normalize casing for low-cardinality "categorical-looking" columns
    # (e.g. a status flag), so values that differ only by case -
    # "COMPLETED" / "Completed" / "completed" - collapse into one value
    # everywhere downstream: cleaning, dedup, schema samples sent to the
    # LLM, and any exact-match SQL generated against this data. High-
    # cardinality columns (names, free text) are skipped on purpose, since
    # case is usually meaningful there.
    for col in df.select_dtypes(include="object").columns:
        non_null = df[col].dropna()
        if non_null.empty:
            continue

        nunique = non_null.nunique()
        if nunique == 0:
            continue
        if nunique > MAX_CATEGORY_UNIQUES or (nunique / len(non_null)) > MAX_CATEGORY_UNIQUE_RATIO:
            continue  # looks like free text, names, or identifiers - leave casing alone

        lower_series = non_null.str.lower()
        if lower_series.nunique() == nunique:
            continue  # no case-only duplicates in this column, nothing to do

        # Canonical spelling = the most frequent original casing within each
        # lowercase group (e.g. if "Completed" appears more than "COMPLETED"
        # or "completed", "Completed" becomes the value everyone is mapped to).
        canonical_map = non_null.groupby(lower_series).agg(lambda s: s.value_counts().idxmax()).to_dict()
        normalized = df[col].map(lambda v: canonical_map.get(v.lower(), v) if isinstance(v, str) else v)
        changed = int((normalized != df[col]).fillna(False).sum())
        if changed:
            df[col] = normalized
            report.append({
                "column": col,
                "issue": "inconsistent casing across otherwise-identical values",
                "action": "normalized to the most common casing per value",
                "count": changed,
            })

    # 4. Drop fully empty columns
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    if empty_cols:
        df = df.drop(columns=empty_cols)
        report.append({"column": empty_cols, "issue": "entirely empty column(s)", "action": "dropped", "count": len(empty_cols)})

    # 5. Drop fully empty rows
    before_rows = len(df)
    df = df.dropna(axis=0, how="all")
    if len(df) < before_rows:
        report.append({"column": None, "issue": "fully empty row(s)", "action": "dropped", "count": before_rows - len(df)})

    # 6. Drop exact duplicate rows (now benefits from casing already being normalized)
    before_rows = len(df)
    df = df.drop_duplicates()
    if len(df) < before_rows:
        report.append({"column": None, "issue": "exact duplicate rows", "action": "dropped, kept first", "count": before_rows - len(df)})

    # 7. Drop duplicates by likely ID column (real "id"/"*_id" match only, not substring)
    id_cols = [c for c in df.columns if ID_COLUMN_PATTERN.search(c)]
    if id_cols:
        before_rows = len(df)
        df = df.drop_duplicates(subset=id_cols[0], keep="first")
        if len(df) < before_rows:
            report.append({"column": id_cols[0], "issue": "duplicate ID rows", "action": "dropped, kept first", "count": before_rows - len(df)})

    # 8. Fill missing numeric values with column median
    for col in df.select_dtypes(include=[np.number]).columns:
        missing = df[col].isna().sum()
        if missing:
            df[col] = df[col].fillna(df[col].median())
            report.append({"column": col, "issue": "missing values", "action": "filled with column median", "count": int(missing)})

    # 9. Fill missing categorical/text values with "Unknown"
    for col in df.select_dtypes(include="object").columns:
        missing = df[col].isna().sum()
        if missing:
            df[col] = df[col].fillna("Unknown")
            report.append({"column": col, "issue": "missing values", "action": "filled with 'Unknown'", "count": int(missing)})

    return df.reset_index(drop=True), report