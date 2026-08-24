# sql-runner — Task Split

## Archie (Lead) — Core Logic
- `llm_planner.py` — plan + feasibility check + SQL generation via LLM
- `sql_validator.py` — validate generated SQL only references real schema columns
- `executor.py` — run validated SQL against MySQL, handle errors/edge cases
- Integration — wiring the full pipeline together in `main.py`

## Timi — Foundation
- `ingest.py` — accept CSV/JSON upload, basic parsing
- `schema_infer.py` — detect column names + data types, map to MySQL types
- `db_loader.py` — CREATE TABLE from schema, bulk insert data
- `output_writer.py` — write final result to `.json` file

## Notes
- Timi's output (schema dict + loaded MySQL table) is the input to Archie's side — agree on the schema dict format early.
- Archie's side depends on Timi's schema being correct, so schema_infer.py should be finished/tested first.

## Git Workflow

1. **Pull latest main before starting:**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create your branch:**
   ```bash
   git checkout -b <branch-name>
   ```
   Branch naming:
   - Archie: `feature/llm-planner`, `feature/sql-validator`, `feature/executor`
   - Timi: `feature/ingest`, `feature/schema-infer`, `feature/db-loader`, `feature/output-writer`

3. **Commit your work:**
   ```bash
   git add .
   git commit -m "clear message describing the change"
   git push origin <branch-name>
   ```

4. **Open a Pull Request:**
   - Push your branch, then open a PR on GitHub targeting `main`
   - Add a short description of what the PR does
   - Tag Archie as reviewer

5. **Review & Merge:**
   - Archie reviews every PR before merging
   - No direct pushes to `main` — everything goes through a PR
   - Once approved, merge into `main` (squash merge preferred for a clean history)