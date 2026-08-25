# sql-runner

`sql-runner` is a small, interactive data-analysis pipeline. Give it one or more CSV/JSON files and a plain-English question; it cleans the data, describes each file's columns to an OpenAI-compatible language model, validates the SQL returned by the model (including checking that every referenced column actually exists), runs that SQL in an in-memory DuckDB database, and saves the result as JSON.

The application is read-only from the user's point of view: it does not need a database server, does not persist imported tables, and is intended for exploratory queries — over one dataset, or across several joined datasets, in a single run.

## Features

- CSV and JSON ingestion through Pandas (extension check is case-insensitive).
- Automatic whitespace and blank-value normalization.
- Removal of empty rows, empty columns, exact duplicate rows, and duplicate rows based on the first column that is literally named `id` or ends in `_id` (not just any column containing the letters "id").
- Median imputation for missing numeric values and `Unknown` for missing text values.
- Schema inference for integer, floating-point, boolean, datetime-like, and text columns — date detection now correctly ignores the `Unknown` placeholder so partially-missing date columns aren't mislabeled as text.
- **Multiple files per run.** Each file becomes its own DuckDB table (name derived from the filename), so the model can generate joins and cross-table queries when more than one file is provided.
- Natural-language query planning and SQL generation through the OpenAI Chat Completions API.
- Feasibility responses when the model cannot satisfy a request from the available schema(s).
- Read-only SQL guardrails before execution, including real validation that every column the SQL references actually exists in the schema (previously this check was written but never enforced).
- JSON results containing the generated SQL and a detailed, per-table cleaning report.

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

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Credential passed to the OpenAI client | None |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL | None |
| `OPENAI_MODEL` | Model used for planning and SQL generation | `gpt-4o-mini` |

`app/main.py` calls `load_dotenv()` at startup, so `.env` is loaded automatically. **Do not commit `.env` or real credentials** — add `.env` to `.gitignore` if it isn't already there.

## Running the CLI

From the repository root:

```bash
python -m app.main
```

The program prompts for:

1. One or more paths ending in `.csv` or `.json`, **comma-separated** if more than one.
2. A natural-language operation, such as `Show the average salary by department`.

Single-file example:

```text
File path(s) (csv/json, comma-separated for multiple): test/sample3_employees.csv
What operation would you like to perform? Show the average salary by department
Result written to outputs/result_YYYYMMDD_HHMMSS_ffffff.json
```

Multi-file (join) example:

```text
File path(s) (csv/json, comma-separated for multiple): test/sample2_sales.csv, test/sample2_products.json
What operation would you like to perform? Show total revenue per product name
Result written to outputs/result_YYYYMMDD_HHMMSS_ffffff.json
```

Input paths are interpreted relative to the current working directory. Run the command from the repository root when using the paths above.

## Processing Pipeline

`app.main.run_pipeline_and_answer(filepaths, user_request)` runs these stages in order:

1. **Ingest:** `app.ingest.load_file` calls `pandas.read_csv` for `.csv` files and `pandas.read_json` for `.json` files (case-insensitive match). Other extensions raise `ValueError`. Runs once per input file.
2. **Clean:** `app.data_cleaner.clean_data` copies the DataFrame, applies the cleaning rules below, resets the index, and returns `(cleaned_dataframe, cleaning_report)`. Runs once per input file.
3. **Infer:** `app.schema_infer.infer_schema` creates a schema object containing each remaining column's name and inferred SQL-style type label. Runs once per input file.
4. **Load:** `db.connection.get_connection` creates a shared `duckdb.connect(database=":memory:")` connection. `app.db_loader.load_data` registers each cleaned DataFrame under a sanitized table name derived from its filename (e.g. `sample2_sales.csv` -> `sample2_sales`).
5. **Plan:** `app.llm_planner.plan_and_generate` sends **all** table schemas and the user request to the configured model in one call, so it can plan joins across files. Expects a JSON planning response.
6. **Feasibility gate:** An infeasible plan is printed and the pipeline stops without creating an output file.
7. **Validate:** `app.sql_validator.validate_sql` checks for missing SQL, disallowed write/DDL keywords, that referenced tables are known, and — now enforced — that every referenced column actually exists in the relevant table's schema (including `table.column`-qualified references).
8. **Execute:** `app.executor.run_query` executes the SQL and converts the resulting DataFrame to a list of dictionaries.
9. **Write:** `app.output_writer.write_output` creates `outputs/` if necessary and writes a timestamped JSON file, with per-table cleaning reports merged together and numpy/`NaN` values sanitized so the write can't fail.

Any failure in steps 1–4 is caught and printed per-file instead of raising an unhandled exception.

## Data Cleaning Rules

Cleaning is applied in this order, per input file:

1. Strip leading and trailing whitespace from column names.
2. For object/text columns, convert values to strings, trim whitespace, and treat `nan`, `None`, an empty string, `NaN`, and `null` as missing.
3. Drop columns that are entirely missing.
4. Drop rows that are entirely missing.
5. Drop exact duplicate rows, keeping the first occurrence.
6. Find the first column whose name is exactly `id` or ends in `_id` (case-insensitive) and, if one exists, drop duplicate values in that column, keeping the first row. (Columns that merely contain the letters "id", like `avoid_list`, no longer match.)
7. Fill missing numeric values with that column's median.
8. Fill missing object/text values with `Unknown`.

Each change is recorded as a report item with `column`, `issue`, `action`, and `count`. In the output file, each entry is also tagged with which table it came from.

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

| Pandas dtype | Inferred label |
| --- | --- |
| `int64` | `INT` |
| `float64` | `DECIMAL(12,2)` |
| `bool` | `BOOLEAN` |
| `datetime64[ns]` | `DATETIME` |
| `object` | `VARCHAR(255)` |

Object columns are additionally tested with `pandas.to_datetime`, but only on their real (non-`Unknown`) values — a date column with some missing values that were filled with `Unknown` is now correctly still labeled `DATETIME` instead of falling back to text. Unrecognized dtypes fall back to `VARCHAR(255)`. These labels describe the schema sent to the model; each DataFrame itself is registered directly with DuckDB.

## LLM Planner Contract

The planner uses the OpenAI-compatible `chat.completions.create` API with `temperature=0`. It receives **all** table schemas for the current run and asks for JSON in this form:

```json
{
  "feasible": true,
  "reason": null,
  "tables_used": ["sample2_sales", "sample2_products"],
  "columns_used": ["sample2_sales.product", "sample2_products.name", "sample2_products.price"],
  "operation_type": "join",
  "sql": "SELECT p.name, SUM(s.quantity * p.price) AS total_revenue FROM sample2_sales s JOIN sample2_products p ON s.product = p.name GROUP BY p.name"
}
```

The system prompt instructs the model to use only supplied tables and columns, use explicit joins with real matching keys, group non-aggregated columns, avoid `SELECT *` for aggregate/join queries, and generate only read-only SQL. Empty responses, API errors, invalid JSON, and model responses containing mutating keywords (checked with word-boundary matching, so a column like `updated_at` is no longer falsely flagged) become a safe `feasible: false` fallback.

## Output Format

Successful runs create `outputs/result_YYYYMMDD_HHMMSS_ffffff.json`:

```json
{
  "sql": "SELECT p.name, SUM(s.quantity * p.price) AS total_revenue FROM sample2_sales s JOIN sample2_products p ON s.product = p.name GROUP BY p.name",
  "result": [
    {"name": "Laptop", "total_revenue": 15050.4}
  ],
  "data_cleaned": true,
  "cleaning_report": [
    {"table": "sample2_sales", "column": "quantity", "issue": "missing values", "action": "filled with column median", "count": 1}
  ]
}
```

`data_cleaned` is true when the combined cleaning report is non-empty. Decimals, dates, numpy scalar types, and `NaN` values are all sanitized to valid, natively JSON-serializable values before writing. Failed feasibility, validation, or execution checks print an error and return without writing a result file.

## Repository Guide

```text
sql-runner/
|-- app/
|   |-- main.py            CLI entry point and multi-file pipeline orchestration
|   |-- ingest.py          CSV/JSON loading into Pandas
|   |-- data_cleaner.py    normalization, deduplication, imputation, reporting
|   |-- schema_infer.py    Pandas dtype to SQL-style schema conversion
|   |-- db_loader.py       DataFrame registration in DuckDB, table-name sanitization
|   |-- llm_planner.py     prompt, model call, response parsing, safety fallback
|   |-- sql_validator.py   table/column/keyword checks before SQL execution
|   |-- executor.py        DuckDB execution and record conversion
|   `-- output_writer.py   timestamped JSON result serialization
|-- db/
|   `-- connection.py      shared in-memory DuckDB connection factory
|-- test/                  sample CSV and JSON input fixtures; no test runner files currently exist
|-- outputs/               checked-in example result JSON artifacts from prior runs
|-- SQL/                   currently empty placeholder directory
|-- gen/                   currently empty placeholder directory
|-- env.example            example LLM environment variables
|-- requirements.txt       runtime Python dependencies
|-- task.md                original team task split and Git workflow notes (predates the DuckDB/multi-table design)
`-- README.md              project documentation
```

### Sample Inputs

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

Pairs like `sample2_sales.csv` + `sample2_products.json` are good candidates for testing the multi-file join path.

## Programmatic Usage

```python
from app.main import run_pipeline_and_answer

run_pipeline_and_answer(
    ["test/sample3_employees.csv"],
    "List the number of employees in each department",
)

# or, joined across two files:
run_pipeline_and_answer(
    ["test/sample2_sales.csv", "test/sample2_products.json"],
    "Show total revenue per product name",
)
```

For lower-level use, the main building blocks are `load_file`, `clean_data`, `infer_schema`, `load_data`, `plan_and_generate`, `validate_sql`, `run_query`, and `write_output`.

## Safety and Current Limitations

- DuckDB is in-memory, so imported data disappears when the process exits and no database credentials are needed.
- The CLI supports only `.csv` and `.json` suffixes and uses Pandas' default parsing behavior.
- The SQL validator blocks `DROP`, `DELETE`, `TRUNCATE`, `ALTER`, `UPDATE`, `INSERT`, `CREATE`, and `REPLACE` (word-boundary matched), requires every referenced table to be a known table, and now rejects unknown/hallucinated column identifiers instead of silently allowing them through.
- The validator strips quoted string literals before checking identifiers, but it is still a lightweight checker, not a full SQL parser — unusual SQL constructs may need further hardening before this is treated as a hard security boundary.
- The planner prompt requests case-insensitive matching, but the application does not independently rewrite or verify every generated string predicate.
- There is no automated unit-test suite, packaging metadata, lockfile, or web interface in the current repository. The `test/` directory is fixture data rather than executable tests.
- `task.md` contains historical MySQL wording from an earlier design; the implementation uses DuckDB and registers Pandas DataFrames instead of creating MySQL tables.
- `.env` should be added to `.gitignore` if it isn't already, since it holds a real API credential.

## Troubleshooting

**`Unsupported file type`**
Use a path whose final extension is `.csv` or `.json` (case-insensitive).

**`Could not read/clean/infer schema for '<path>'`**
One of the input files failed at ingestion, cleaning, or schema inference — check the printed error for the underlying cause (bad path, malformed file, unsupported structure).

**`LLM request failed`**
Check `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, network access, and whether the configured endpoint implements the OpenAI Chat Completions API.

**`Not feasible`**
The model could not map the request to the supplied schema(s), returned an invalid response, or blocked the request as unsafe. Use the exact column names visible in the input file(s) and ask for a read-only analysis.

**`Invalid SQL`**
The validator rejected the generated SQL — commonly an unknown table/column reference or a disallowed keyword. The reason string explains which check failed.

**`Execution error`**
The model produced SQL that passed validation but that DuckDB itself rejected (e.g. a type mismatch). The generated SQL is included only in successful output files, so rerun with a simpler request and inspect the endpoint/model response if needed.

## Development Checks

There is currently no configured test command. A basic import smoke check is:

```bash
python -c "import pandas, duckdb, openai, dotenv; from app.data_cleaner import clean_data; from app.schema_infer import infer_schema; print('imports ok')"
```

