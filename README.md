# sql-runner

`sql-runner` is a small, interactive data-analysis pipeline. Give it one CSV or JSON file and a plain-English question; it cleans the data, describes its columns to an OpenAI-compatible language model, validates the SQL returned by the model, runs that SQL in an in-memory DuckDB database, and saves the result as JSON.

The application is read-only from the user's point of view: it does not need a database server, does not persist an imported table, and is intended for exploratory queries over one uploaded dataset at a time.

## Features

- CSV and JSON ingestion through Pandas.
- Automatic whitespace and blank-value normalization.
- Removal of empty rows, empty columns, exact duplicate rows, and duplicate rows based on the first column whose name contains `id`.
- Median imputation for missing numeric values and `Unknown` for missing text values.
- Basic schema inference for integer, floating-point, boolean, datetime-like, and text columns.
- In-memory DuckDB execution with the imported DataFrame exposed as `uploaded_data`.
- Natural-language query planning and SQL generation through the OpenAI Chat Completions API.
- Feasibility responses when the model cannot satisfy a request from the available schema.
- Read-only SQL guardrails before execution.
- JSON results containing the generated SQL and a detailed cleaning report.

## Requirements

- Python 3.10 or newer. The code uses the Python 3.10 union type syntax (`list | None`).
- The dependencies in `requirements.txt`.
- Access to an OpenAI-compatible Chat Completions endpoint. A real API key is required by most hosted endpoints; a local or custom endpoint may use its own authentication rules.

## Installation

```bash
git clone <repository-url>
cd sql-runner
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux/Git Bash
source .venv/bin/activate
```

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

## Configuration

Copy `env.example` to `.env` in the project root and fill in the values:

```powershell
Copy-Item env.example .env
```

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Configuration variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Credential passed to the OpenAI client | None |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL | None |
| `OPENAI_MODEL` | Model used for planning and SQL generation | `gpt-4o-mini` |

`app/main.py` calls `load_dotenv()` at startup, so `.env` is loaded automatically. Do not commit `.env` or real credentials. The checked-in `env.example` contains a project-specific custom endpoint and model placeholder; replace those values for your environment.

## Running the CLI

From the repository root:

```bash
python -m app.main
```

The program prompts for:

1. A path ending in `.csv` or `.json`.
2. A natural-language operation, such as `Show the average salary by department`.

Example using a checked-in fixture:

```text
File path (csv/json): test/sample3_employees.csv
What operation would you like to perform? Show the average salary by department
Result written to outputs/result_YYYYMMDD_HHMMSS.json
```

Input paths are interpreted relative to the current working directory. Run the command from the repository root when using the paths above. The CLI currently processes one file and one table per invocation; it does not discover fixtures in `test/` or join multiple uploaded files automatically.

## Processing Pipeline

`app.main.run_pipeline(filepath, user_request)` runs these stages in order:

1. **Ingest:** `app.ingest.load_file` calls `pandas.read_csv` for `.csv` files and `pandas.read_json` for `.json` files. Other extensions raise `ValueError`.
2. **Clean:** `app.data_cleaner.clean_data` copies the DataFrame, applies the cleaning rules below, resets the index, and returns `(cleaned_dataframe, cleaning_report)`.
3. **Infer:** `app.schema_infer.infer_schema` creates a schema object containing each remaining column's name and inferred SQL-style type label.
4. **Load:** `db.connection.get_connection` creates a new `duckdb.connect(database=":memory:")` connection. `app.db_loader.load_data` registers the DataFrame under the table name `uploaded_data`.
5. **Plan:** `app.llm_planner.plan_and_generate` sends the schema and user request to the configured model. It expects a JSON planning response.
6. **Feasibility gate:** An infeasible plan is printed and the pipeline stops without creating an output file.
7. **Validate:** `app.sql_validator.validate_sql` checks for missing SQL, the expected table name, and disallowed write/DDL keywords.
8. **Execute:** `app.executor.run_query` executes the SQL and converts the resulting DataFrame to a list of dictionaries.
9. **Write:** `app.output_writer.write_output` creates `outputs/` if necessary and writes a timestamped JSON file.

## Data Cleaning Rules

Cleaning is applied in this order:

1. Strip leading and trailing whitespace from column names.
2. For object/text columns, convert values to strings, trim whitespace, and treat `nan`, `None`, an empty string, `NaN`, and `null` as missing.
3. Drop columns that are entirely missing.
4. Drop rows that are entirely missing.
5. Drop exact duplicate rows, keeping the first occurrence.
6. Find column names containing `id` case-insensitively and, if any exist, drop duplicate values using only the first matching column, keeping the first row.
7. Fill missing numeric values with that column's median.
8. Fill missing object/text values with `Unknown`.

Each change is recorded as a report item with `column`, `issue`, `action`, and `count`. This report is returned even when no rows or values were changed.

## Schema Inference

The inferred schema has this shape:

```json
{
  "columns": [
    {"name": "employee_id", "type": "INT"},
    {"name": "salary", "type": "DECIMAL(12,2)"},
    {"name": "active", "type": "BOOLEAN"},
    {"name": "joined_at", "type": "DATETIME"},
    {"name": "department", "type": "VARCHAR(255)"}
  ]
}
```

The current mapping is based on Pandas dtype strings:

| Pandas dtype | Inferred label |
| --- | --- |
| `int64` | `INT` |
| `float64` | `DECIMAL(12,2)` |
| `bool` | `BOOLEAN` |
| `datetime64[ns]` | `DATETIME` |
| `object` | `VARCHAR(255)` |

Object columns are additionally tested with `pandas.to_datetime`; columns for which every value parses are labeled `DATETIME`. Unrecognized dtypes fall back to `VARCHAR(255)`. These labels describe the schema sent to the model; the DataFrame itself is registered directly with DuckDB.

## LLM Planner Contract

The planner uses the OpenAI-compatible `chat.completions.create` API with `temperature=0`. It asks for JSON in this form:

```json
{
  "feasible": true,
  "reason": null,
  "tables_used": ["uploaded_data"],
  "columns_used": ["uploaded_data.department", "uploaded_data.salary"],
  "operation_type": "aggregation",
  "sql": "SELECT department, AVG(salary) AS average_salary FROM uploaded_data GROUP BY department"
}
```

The system prompt instructs the model to use only supplied tables and columns, use explicit joins, group non-aggregated columns, avoid `SELECT *` for aggregate/join queries, and generate only read-only SQL. Empty responses, API errors, invalid JSON, and model responses containing mutating keywords become a safe `feasible: false` fallback.

## Output Format

Successful runs create `outputs/result_YYYYMMDD_HHMMSS.json`:

```json
{
  "sql": "SELECT department, AVG(salary) AS average_salary FROM uploaded_data GROUP BY department",
  "result": [
    {"department": "Engineering", "average_salary": 92500.0}
  ],
  "data_cleaned": true,
  "cleaning_report": [
    {
      "column": "salary",
      "issue": "missing values",
      "action": "filled with column median",
      "count": 1
    }
  ]
}
```

`data_cleaned` is true when the cleaning report is non-empty. Dates and decimals that are not natively JSON serializable are converted to strings by `output_writer._default`. Failed feasibility, validation, or execution checks print an error and return without writing a result file.

## Repository Guide

```text
sql-runner/
|-- app/
|   |-- main.py            CLI entry point and pipeline orchestration
|   |-- ingest.py          CSV/JSON loading into Pandas
|   |-- data_cleaner.py    normalization, deduplication, imputation, reporting
|   |-- schema_infer.py    Pandas dtype to SQL-style schema conversion
|   |-- db_loader.py       DataFrame registration in DuckDB
|   |-- llm_planner.py     prompt, model call, response parsing, safety fallback
|   |-- sql_validator.py   table/keyword checks before SQL execution
|   |-- executor.py        DuckDB execution and record conversion
|   `-- output_writer.py   timestamped JSON result serialization
|-- db/
|   `-- connection.py      new shared in-memory DuckDB connection factory
|-- test/                  sample CSV and JSON input fixtures; no test runner files currently exist
|-- outputs/               checked-in example result JSON artifacts from prior runs
|-- SQL/                   currently empty placeholder directory
|-- gen/                   currently empty placeholder directory
|-- env.example            example LLM environment variables
|-- requirements.txt       runtime Python dependencies
|-- task.md                original team task split and Git workflow notes
`-- README.md              project documentation
```

### Sample Inputs

The `test/` directory contains the following fixtures:

| File | Format | Subject |
| --- | --- | --- |
| `sample1_simple.csv` | CSV | Basic tabular data |
| `sample1_cities.json` | JSON | City records |
| `sample2_sales.csv` | CSV | Sales records |
| `sample2_products.json` | JSON | Product records |
| `sample3_employees.csv` | CSV | Employee records |
| `sample3_users.json` | JSON | User records |
| `sample4_students.csv` | CSV | Student records |
| `sample4_vehicles.json` | JSON | Vehicle records |
| `sample5_transactions.csv` | CSV | Transaction records |
| `sample5_tickets.json` | JSON | Ticket records |
| `dirty_employees_v1.csv` | CSV | Deliberately messy employee data for cleaning behavior |

The `outputs/` directory currently contains six timestamped JSON artifacts. They are examples of the writer's output contract, not a reproducible test suite. `SQL/` and `gen/` exist in the repository but currently contain no files.

## Programmatic Usage

The orchestration function can be called from Python:

```python
from app.main import run_pipeline

run_pipeline(
    "test/sample3_employees.csv",
    "List the number of employees in each department",
)
```

For lower-level use, the main building blocks are `load_file`, `clean_data`, `infer_schema`, `load_data`, `plan_and_generate`, `validate_sql`, `run_query`, and `write_output`. `plan_and_generate` accepts a schema dictionary with one or more tables, but the current `run_pipeline` wires only the single table `uploaded_data` into it.

## Safety and Current Limitations

- DuckDB is in-memory, so imported data disappears when the process exits and no database credentials are needed.
- The CLI supports only `.csv` and `.json` suffixes and uses Pandas' default parsing behavior.
- The current pipeline imports one file per run and does not expose a multi-table join workflow, even though the planner prompt describes multi-table joins.
- The SQL validator blocks `DROP`, `DELETE`, `TRUNCATE`, `ALTER`, `UPDATE`, and `INSERT`, and requires `uploaded_data` to appear in the SQL.
- The validator's column-token loop is intentionally permissive and currently does not reject unknown column identifiers. It should be tightened before treating it as a complete SQL parser or security boundary.
- The planner prompt requests case-insensitive matching, but the application does not independently rewrite or verify every generated string predicate.
- There is no automated unit-test suite, packaging metadata, lockfile, or web interface in the current repository. The `test/` directory is fixture data rather than executable tests.
- `task.md` contains historical MySQL wording; the implementation uses DuckDB and registers Pandas DataFrames instead of creating MySQL tables.

## Troubleshooting

**`Unsupported file type`**

Use a path whose final extension is exactly `.csv` or `.json`.

**`LLM request failed`**

Check `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, network access, and whether the configured endpoint implements the OpenAI Chat Completions API.

**`Not feasible`**

The model could not map the request to the supplied schema, returned an invalid response, or blocked the request as unsafe. Use the exact column names visible in the input file and ask for a read-only analysis.

**`Execution error`**

The model produced SQL that DuckDB rejected. The generated SQL is included only in successful output files, so rerun with a simpler request and inspect the endpoint/model response if needed.

## Development Checks

There is currently no configured test command. A basic import smoke check is:

```bash
python -c "import pandas, duckdb, openai, dotenv; from app.data_cleaner import clean_data; from app.schema_infer import infer_schema; print('imports ok')"
```

The recommended next testing additions are unit tests for cleaning and schema inference, validator tests for allowed/disallowed SQL, and an integration test that mocks the LLM response before exercising the full pipeline.
