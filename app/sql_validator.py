"""
sql_validator.py
Sanity-checks LLM-generated SQL before it's executed.
Catches hallucinated tables/columns and disallowed statements.

Now supports multiple tables (for joins) and ACTUALLY rejects unknown
columns instead of silently allowing everything through.
"""

import re

DISALLOWED_KEYWORDS = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT", "CREATE", "REPLACE"]

SQL_RESERVED = {
    "select", "from", "where", "group", "by", "order", "limit", "as", "and", "or",
    "not", "null", "avg", "sum", "count", "min", "max", "distinct", "asc", "desc",
    "having", "join", "inner", "left", "right", "full", "outer", "on", "case",
    "when", "then", "else", "end", "is", "in", "between", "like", "true", "false",
    "cast", "coalesce", "over", "partition", "with", "union", "all", "exists",
}


def validate_sql(sql: str, schemas: dict, tables_used: list | None = None) -> dict:
    """
    schemas: {"table_name": {"columns": [{"name": ..., "type": ...}, ...]}, ...}
             (pass a single-table dict for single-table use cases, same as before)
    tables_used: tables the LLM said it used; if omitted, all known tables are allowed

    Returns {"valid": bool, "reason": str or None}
    """
    if not sql or not sql.strip():
        return {"valid": False, "reason": "No SQL provided."}

    upper_sql = sql.upper()

    # Block destructive/write operations - this tool is read-only
    for keyword in DISALLOWED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            return {"valid": False, "reason": f"Disallowed operation: {keyword}"}

    known_tables = set(schemas.keys())
    referenced_tables = set(tables_used) if tables_used else known_tables
    unknown_tables = referenced_tables - known_tables
    if unknown_tables:
        return {"valid": False, "reason": f"Query references unknown table(s): {', '.join(sorted(unknown_tables))}"}

    if not any(t.lower() in sql.lower() for t in known_tables):
        return {"valid": False, "reason": "Query does not reference any known table."}

    # Remove string literals so words INSIDE quotes ('Engineering', etc.)
    # never get mistaken for column/table identifiers.
    sql_no_strings = re.sub(r"'[^']*'", " ", sql)

    valid_bare_columns = set()
    valid_qualified_columns = set()
    for table, schema in schemas.items():
        for col in schema["columns"]:
            name = col["name"].lower()
            valid_bare_columns.add(name)
            valid_qualified_columns.add(f"{table.lower()}.{name}")

    table_name_tokens = {t.lower() for t in known_tables}

    # Check table.column style references
    qualified_refs = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b", sql_no_strings)
    for tbl, col in qualified_refs:
        ref = f"{tbl.lower()}.{col.lower()}"
        if tbl.lower() in table_name_tokens and ref not in valid_qualified_columns:
            return {"valid": False, "reason": f"Unknown column '{col}' on table '{tbl}'."}

    # Drop the qualified refs so their column half isn't re-checked as a bare token
    sql_bare_only = re.sub(r"\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\b", " ", sql_no_strings)
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql_bare_only)

    lowered_sql = sql_bare_only.lower()
    for token in tokens:
        t = token.lower()
        if t in SQL_RESERVED or t in table_name_tokens or t in valid_bare_columns:
            continue
        if t.isdigit():
            continue
        # If immediately followed by "(", treat it as a function call (e.g. STRFTIME(...))
        idx = lowered_sql.find(t)
        next_char = lowered_sql[idx + len(t): idx + len(t) + 1] if idx != -1 else ""
        if next_char.strip() == "(":
            continue
        return {"valid": False, "reason": f"Unknown column or identifier: '{token}'."}

    return {"valid": True, "reason": None}