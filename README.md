# sql-runner

A tool that ingests a CSV or JSON file, infers the column schema (names + data types), suggests possible SQL operations based on that schema, generates SQL using an LLM, validates and runs it against MySQL, and writes the result to a `.json` output file.

## How It Works

1. **Ingest** — Upload a CSV or JSON file.
2. **Infer Schema** — Detect column names and data types (int, float, varchar, date, boolean, etc.) and map them to MySQL types.
3. **Load** — Create a MySQL table from the inferred schema and bulk-insert the data.
4. **Suggest Operations** — A rules engine suggests SQL operations valid for each column type (e.g. SUM/AVG for numeric, GROUP BY/DISTINCT for categorical, date-range filters for dates).
5. **Free-Form Requests** — Users aren't limited to the suggested list. Any operation can be requested in plain English.
6. **Plan + Generate (LLM)** — The LLM is given the schema and the request, and first produces a plan (columns needed, operation type, feasibility) before generating SQL. This improves accuracy and catches unsupported requests early.
7. **Feasibility Check** — If the schema can't support the request, the tool tells the user the data provided is insufficient, instead of guessing or hallucinating columns.
8. **Validate** — Generated SQL is checked to ensure it only references columns that actually exist in the schema, before execution.
9. **Execute** — The validated SQL is run against MySQL.
10. **Output** — Results are written to a `.json` file in `outputs/`, alongside the SQL that was run.

## Project Structure

```
sql-runner/
├── app/
│   ├── main.py              # entrypoint (API or CLI)
│   ├── ingest.py            # file upload, CSV/JSON parsing
│   ├── schema_infer.py      # column/type detection, pandas→MySQL type map
│   ├── db_loader.py         # CREATE TABLE + bulk insert into MySQL
│   ├── operations.py        # rules engine: suggest ops from schema
│   ├── llm_planner.py       # plan + feasibility + SQL generation (LLM calls)
│   ├── sql_validator.py     # check generated SQL only refs real columns
│   ├── executor.py          # run SQL, fetch results
│   └── output_writer.py     # write result to .json
├── db/
│   └── connection.py        # MySQL connector/engine setup
├── uploads/                 # incoming CSV/JSON files
├── outputs/                 # generated .json result files
├── tests/
│   ├── test_schema_infer.py
│   ├── test_operations.py
│   └── test_executor.py
├── .env                     # DB creds, LLM API key
├── requirements.txt
└── README.md
```

## Setup

### Prerequisites
- Python 3.10+
- MySQL server (local or remote)
- LLM API key (for SQL generation)

### Installation
```bash
git clone <repo-url>
cd sql-runner
pip install -r requirements.txt
```

### Environment Variables
Create a `.env` file in the project root:
```
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=sql_schema_tool
LLM_API_KEY=your_llm_api_key
```

## Usage

1. Upload a CSV or JSON file.
2. The tool infers the schema and loads the data into MySQL.
3. Review the suggested operations, or type your own request in plain English.
4. The tool plans, generates, validates, and executes the SQL.
5. Check `outputs/` for the resulting `.json` file (contains the SQL run and the result set).

Example output file:
```json
{
  "sql": "SELECT AVG(age) FROM users WHERE country = 'NG';",
  "result": [
    { "AVG(age)": 27.4 }
  ]
}
```

## Type Mapping (pandas → MySQL)

| Pandas dtype | MySQL type |
|---|---|
| int64 | INT |
| float64 | DECIMAL / FLOAT |
| object (text) | VARCHAR |
| object (date-like) | DATETIME |
| bool | BOOLEAN |



## Notes / Guardrails

- The LLM is never allowed to guess column names — the real schema is always injected into its prompt.
- Generated SQL is validated against the schema before execution, to catch hallucinated columns.
- If a requested operation isn't feasible with the given data, the user is told directly rather than receiving a broken or hallucinated query.
- Non-JSON-serializable MySQL result types (e.g. `Decimal`, `datetime`) are cast to strings before writing output.

## Roadmap

- [ ] CSV support (first)
- [ ] JSON support
- [ ] Free-form / feasibility-checked operations
- [ ] Plan-then-generate LLM flow
- [ ] Output written to `.json` file