"""
main.py
Orchestrates the 2FA Data Analysis Pipeline.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app.ingest import load_file
from app.data_cleaner import clean_data
from app.schema_infer import infer_schema
from app.db_loader import load_data, sanitize_table_name
from app.llm_planner import rewrite_query, plan_and_generate
from app.sql_validator import validate_sql
from app.executor import run_query
from app.output_writer import write_output
from db.connection import get_connection

def _unique_table_name(path: str, used_names: set) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    name = sanitize_table_name(base)
    original = name
    i = 2
    while name in used_names:
        name = f"{original}_{i}"
        i += 1
    used_names.add(name)
    return name

def run_pipeline(filepaths: list):
    conn = get_connection()
    schemas = {}
    cleaning_reports = {}
    used_names = set()

    for raw_path in filepaths:
        path = raw_path.strip()
        if not path:
            continue

        try:
            df = load_file(path)
            df, report = clean_data(df)
            schema = infer_schema(df)
            table_name = _unique_table_name(path, used_names)
            load_data(df, table_name, conn)
            
            schemas[table_name] = schema
            cleaning_reports[table_name] = report
        except Exception as e:
            print(f"Could not process '{path}': {e}")
            return False

    if not schemas:
        print("No valid files were loaded.")
        return False

    return schemas, cleaning_reports, conn

def run_pipeline_and_answer(filepaths: list, user_request: str):
    prep = run_pipeline(filepaths)
    if prep is False:
        return
    schemas, cleaning_reports, conn = prep

    print(f"\n[Raw Query]: {user_request}")
    explicit_instructions = rewrite_query(schemas, user_request)
    print(f"[Interpreted Context]: {explicit_instructions}\n")

    plan = plan_and_generate(schemas, explicit_instructions)
    if not plan.get("feasible"):
        print(f"Not feasible: {plan.get('reason')}")
        return

    # FIX: Use 'or default' to satisfy Pylance type requirements
    sql = plan.get("sql") or ""
    tables_used = plan.get("tables_used") or []
    
    validation = validate_sql(sql, schemas, tables_used)
    if not validation.get("valid"):
        print(f"Invalid SQL: {validation.get('reason')}")
        return

    outcome = run_query(sql, conn)
    if not outcome.get("success"):
        print(f"Execution error: {outcome.get('error')}")
        return

    combined_report = [
        {"table": table, **entry}
        for table, entries in cleaning_reports.items()
        for entry in entries
    ]

    result_data = outcome.get("result") or []
    filepath_out = write_output(sql, result_data, combined_report)
    print(f"Result written to {filepath_out}")

if __name__ == "__main__":
    raw_paths = input("File path(s) (csv/json, comma-separated for multiple): ")
    file_paths = raw_paths.split(",")
    request = input("What operation would you like to perform? ")
    run_pipeline_and_answer(file_paths, request)