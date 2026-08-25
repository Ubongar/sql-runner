"""
sql_validator.py
Sanity-checks LLM-generated SQL before it's executed using SQLGlot.
Now supports validating multiple semicolon-separated SELECT statements in a single pass.
"""

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.errors import ParseError, OptimizeError


def validate_sql(sql: str, schemas: dict, tables_used: list | None = None) -> dict:
    if not sql or not sql.strip():
        return {"valid": False, "reason": "No SQL provided."}

    # 1. Parse the SQL string into a list of ASTs (supports multiple statements)
    try:
        expressions = sqlglot.parse(sql, dialect="duckdb")
    except ParseError as e:
        return {"valid": False, "reason": f"SQL syntax error: {str(e)}"}

    # Filter out empty statements (e.g., a trailing semicolon)
    expressions = [expr for expr in expressions if expr]
    if not expressions:
        return {"valid": False, "reason": "No valid SQL statements found."}

    # Dynamically build the list of mutating operations
    mutating_classes = []
    for cls_name in ["Insert", "Update", "Delete", "Drop", "Alter", "AlterTable", "AlterColumn", "Create", "Command"]:
        if hasattr(exp, cls_name):
            mutating_classes.append(getattr(exp, cls_name))
    mutating_types = tuple(mutating_classes)

    # Format the schema for SQLGlot's Optimizer
    sqlglot_schema = {}
    for table_name, table_def in schemas.items():
        sqlglot_schema[table_name] = {col["name"]: col["type"] for col in table_def["columns"]}

    # Validate EVERY statement in the query
    for expression in expressions:
        # 2. Enforce Read-Only Operations
        if not isinstance(expression, (exp.Select, exp.Union)):
            return {"valid": False, "reason": f"Only SELECT queries are allowed. Found: {type(expression).__name__}"}
            
        for node_type in mutating_types:
            if expression.find(node_type):
                return {"valid": False, "reason": f"Disallowed write operation detected: {node_type.__name__}"}

        # 3. Semantically Validate Columns and Tables
        try:
            qualify(expression, dialect="duckdb", schema=sqlglot_schema, validate_qualify_columns=True)
        except OptimizeError as e:
            return {"valid": False, "reason": f"Schema validation error: {str(e)}"}
        except Exception as e:
            return {"valid": False, "reason": f"Unexpected validation error: {str(e)}"}

    return {"valid": True, "reason": None}