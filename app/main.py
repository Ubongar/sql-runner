"""
main.py
Wires the full pipeline: ingest -> clean -> schema -> load (DuckDB) ->
plan/generate -> validate -> execute -> output.

Now supports ONE OR MORE input files. Each file becomes its own DuckDB
table, so if you provide more than one file, the language model can
generate joins and cross-table queries against all of them at once.
"""
from dotenv import load_dotenv
load_dotenv()

import os

from app.ingest import load_file
from app.data_cleaner import clean_data
from app.schema_infer import infer_schema
from app.db_loader import load_data, sanitize_table_name
from app.llm_planner import plan_and_generate
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
    """
    filepaths: list of one or more csv/json file paths.
    Returns True on success, False if the pipeline stopped early
    (all failure reasons are printed as they happen).
    """
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
        except Exception as e:
            print(f"Could not read '{path}': {e}")
            return False

        try:
            df, report = clean_data(df)
        except Exception as e:
            print(f"Could not clean data from '{path}': {e}")
            return False

        try:
            schema = infer_schema(df)
        except Exception as e:
            print(f"Could not infer schema for '{path}': {e}")
            return False

        table_name = _unique_table_name(path, used_names)

        try:
            load_data(df, table_name, conn)
        except Exception as e:
            print(f"Could not load '{path}' into DuckDB: {e}")
            return False

        schemas[table_name] = schema
        cleaning_reports[table_name] = report

    if not schemas:
        print("No valid files were loaded.")
        return False

    return schemas, cleaning_reports, conn


def run_pipeline_and_answer(filepaths: list, user_request: str):
    prep = run_pipeline(filepaths)
    if prep is False:
        return
    schemas, cleaning_reports, conn = prep

    plan = plan_and_generate(schemas, user_request)
    if not plan["feasible"]:
        print(f"Not feasible: {plan['reason']}")
        return

    validation = validate_sql(plan["sql"], schemas, plan.get("tables_used"))
    if not validation["valid"]:
        print(f"Invalid SQL: {validation['reason']}")
        return

    outcome = run_query(plan["sql"], conn)
    if not outcome["success"]:
        print(f"Execution error: {outcome['error']}")
        return

    combined_report = [
        {"table": table, **entry}
        for table, entries in cleaning_reports.items()
        for entry in entries
    ]

    filepath_out = write_output(plan["sql"], outcome["result"], combined_report)
    print(f"Result written to {filepath_out}")


if __name__ == "__main__":
    raw_paths = input("File path(s) (csv/json, comma-separated for multiple): ")
    file_paths = raw_paths.split(",")
    request = input("What operation would you like to perform? ")
    run_pipeline_and_answer(file_paths, request)