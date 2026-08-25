"""
llm_planner.py
Implements a 2-step AI architecture:
1. Rewriter: Interprets user intent using schema metadata.
2. Generator: Produces strictly valid DuckDB SQL.
"""

import json
import os
import sys
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Fixes "same prompt, different result" between runs/users: most OpenAI-compatible
# backends use this to make temperature=0 output far more consistent run-to-run.
# It's not an absolute guarantee, but it meaningfully tightens reproducibility.
# Override with OPENAI_SEED in .env if you want a different fixed seed.
SEED = int(os.getenv("OPENAI_SEED", "42"))

SQL_SYSTEM_PROMPT = """You are a strict DuckDB-compatible SQL planner and generator.
Respond ONLY with valid JSON containing the following shape:
{
  "feasible": true/false,
  "reason": "explanation if false",
  "tables_used": ["table1"],
  "columns_used": ["table1.col"],
  "operation_type": "aggregation | filter | join | group_by | subquery | window | other",
  "sql": "the strictly valid DuckDB SQL"
}

HARD RULES:
1. ONLY reference provided tables and columns.
2. Group all non-aggregated columns.
3. Explicit JOIN syntax only. Always alias tables.
4. Read-only queries only.
"""


def rewrite_query(schemas: dict, raw_request: str) -> str:
    system_prompt = """You are a Data Analysis Contextualizer. Your job is to rewrite the user's raw query into highly specific, unambiguous instructions for a SQL generation agent.
    1. Analyze the provided schema, including data samples and min/max boundaries.
    2. Resolve ambiguities explicitly (e.g., if the user asks for 'February' but the data only spans '2023-01' to '2023-06', specify 'between 2023-02-01 and 2023-02-28').
    3. Map casual terms to actual column names and sample values.
    4. CASE VARIANTS: If a column's sample values include what look like the same
       value spelled with different capitalization (e.g. "COMPLETED", "Completed",
       "completed"), explicitly instruct the SQL generator to match that value
       case-insensitively (e.g. "match status using LOWER(status) = 'completed'"),
       never as a single exact-case equality check.
    5. Return ONLY the explicit rewritten instructions, no preamble.
    6. MULTIPLE QUERIES: If the user asks for multiple completely unrelated datasets that cannot be logically joined, you MUST output multiple SELECT statements separated by a semicolon (;)."""

    user_prompt = f"Schema & Metadata: {json.dumps(schemas)}\nRaw Request: {raw_request}"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            seed=SEED,
        )
        content = response.choices[0].message.content

        if not content or not content.strip():
            # Previously silent: two users hitting an empty-response run would
            # get inconsistent behavior (one rewritten, one not) with no trace of why.
            print(
                "[rewrite_query] Rewriter returned an empty response - "
                "falling back to the raw, unrewritten request. Downstream SQL "
                "generation will be less precise for this run.",
                file=sys.stderr,
            )
            return raw_request

        return content.strip()

    except Exception as e:
        # Previously: `except Exception: return raw_request` - completely silent.
        # Now visible, so a flaky rewrite call is distinguishable from normal
        # LLM variance when comparing why two runs of the "same" prompt differed.
        print(
            f"[rewrite_query] Rewrite step failed ({e}) - falling back to the raw, "
            f"unrewritten request. Downstream SQL generation will be less precise "
            f"for this run.",
            file=sys.stderr,
        )
        return raw_request


def plan_and_generate(schemas: dict, user_request: str) -> dict:
    user_prompt = f"Table schemas: {json.dumps(schemas)}\nExplicit Instructions: {user_request}"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SQL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            seed=SEED,
        )
        content = response.choices[0].message.content
        raw = content.strip() if content else ""

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()

        parsed = json.loads(raw)
        parsed.setdefault("feasible", False)
        parsed.setdefault("reason", None)
        parsed.setdefault("tables_used", [])
        parsed.setdefault("columns_used", [])
        parsed.setdefault("operation_type", None)
        parsed.setdefault("sql", None)
        return parsed

    except Exception as e:
        return _fallback(f"LLM request or parsing failed: {e}")


def _fallback(reason: str) -> dict:
    return {
        "feasible": False,
        "reason": reason,
        "tables_used": [],
        "columns_used": [],
        "operation_type": None,
        "sql": None,
    }