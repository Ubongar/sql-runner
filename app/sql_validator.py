"""
sql_validator.py
Sanity-checks LLM-generated SQL before it's executed using SQLGlot.
Catches hallucinated tables/columns and ensures the query is strictly read-only.
"""

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.errors import ParseError, OptimizeError


def validate_sql(sql: str, schemas: dict, tables_used: list | None = None) -> dict:
    """
    schemas: {"table_name": {"columns": [{"name": ..., "type": ...}, ...]}, ...}
    tables_used: optional list of tables the LLM said it used.
    
    Returns {"valid": bool, "reason": str or None}
    """
    if not sql or not sql.strip():
        return {"valid": False, "reason": "No SQL provided."}

    # 1. Parse the SQL query into an Abstract Syntax Tree (AST)
    try:
        # We explicitly tell it to parse using DuckDB rules
        expression = sqlglot.parse_one(sql, dialect="duckdb")
    except ParseError as e:
        return {"valid": False, "reason": f"SQL syntax error: {str(e)}"}

    # 2. Enforce Read-Only Operations (Block DML/DDL)
    # The root of the query MUST be a Select or Union of Selects
    if not isinstance(expression, (exp.Select, exp.Union)):
        return {"valid": False, "reason": "Only SELECT queries are allowed."}
        
    # Dynamically build the list of mutating operations so it works across ALL sqlglot versions
    mutating_classes = []
    for cls_name in ["Insert", "Update", "Delete", "Drop", "Alter", "AlterTable", "AlterColumn", "Create", "Command"]:
        if hasattr(exp, cls_name):
            mutating_classes.append(getattr(exp, cls_name))
            
    mutating_types = tuple(mutating_classes)
    
    # Walk the tree to ensure no mutating commands are nested anywhere inside
    for node_type in mutating_types:
        if expression.find(node_type):
            return {"valid": False, "reason": f"Disallowed write operation detected: {node_type.__name__}"}

    # 3. Format the schema for SQLGlot's Optimizer
    # Converts from your app's structure: {"table": {"columns": [{"name": "col1", "type": "INT"}]}}
    # To SQLGlot's expected structure:   {"table": {"col1": "INT"}}
    sqlglot_schema = {}
    for table_name, table_def in schemas.items():
        sqlglot_schema[table_name] = {
            col["name"]: col["type"] for col in table_def["columns"]
        }

    # 4. Semantically Validate Columns and Tables
    try:
        # qualify() resolves all aliases, CTEs, and checks against the schema
        qualify(
            expression, 
            dialect="duckdb", 
            schema=sqlglot_schema,
            validate_qualify_columns=True
        )
    except OptimizeError as e:
        return {"valid": False, "reason": f"Schema validation error: {str(e)}"}
    except Exception as e:
        return {"valid": False, "reason": f"Unexpected validation error: {str(e)}"}

    return {"valid": True, "reason": None}