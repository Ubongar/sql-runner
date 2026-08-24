"""
main.py
Wires the full pipeline: ingest -> schema -> load (DuckDB) -> plan/generate -> validate -> execute -> output.
"""
from dotenv import load_dotenv
load_dotenv()

from app.ingest import load_file
from app.data_cleaner import clean_data
from app.schema_infer import infer_schema
from app.db_loader import load_data
from app.llm_planner import plan_and_generate
from app.sql_validator import validate_sql
from app.executor import run_query
from app.output_writer import write_output
from db.connection import get_connection

TABLE_NAME = "uploaded_data"


def run_pipeline(filepath: str, user_request: str):
    df = load_file(filepath)
    df, cleaning_report = clean_data(df)
    schema = infer_schema(df)

    conn = get_connection()
    load_data(df, TABLE_NAME, conn)

    schemas = {TABLE_NAME: schema}
    plan = plan_and_generate(schemas, user_request)
    if not plan["feasible"]:
        print(f"Not feasible: {plan['reason']}")
        return

    validation = validate_sql(plan["sql"], schema, TABLE_NAME)
    if not validation["valid"]:
        print(f"Invalid SQL: {validation['reason']}")
        return

    outcome = run_query(plan["sql"], conn)
    if not outcome["success"]:
        print(f"Execution error: {outcome['error']}")
        return

    filepath_out = write_output(plan["sql"], outcome["result"], cleaning_report)
    print(f"Result written to {filepath_out}")


if __name__ == "__main__":
    file_path = input("File path (csv/json): ")
    request = input("What operation would you like to perform? ")
    run_pipeline(file_path, request)