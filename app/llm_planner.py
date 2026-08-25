"""
llm_planner.py
Takes one or more table schemas + a user's natural-language request.
Asks the LLM to PLAN (feasibility, columns, joins) then GENERATE SQL,
in a single structured response. Handles complex queries:
multi-table joins, aggregates, subqueries, window functions.
"""

import json
import os
import re
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
MODEL = os.getenv("OPENAI_MODEL", "olori-image")

BLOCKED_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "REPLACE")

SYSTEM_PROMPT = """You are a strict DuckDB-compatible SQL planner and generator.

You will receive:
1. One or more table schemas: {"table_name": {"columns": [{"name": str, "type": str}, ...]}, ...}
2. A user's request in plain English

Respond ONLY with valid JSON, no markdown, no code fences, no preamble:
{
  "feasible": true/false,
  "reason": "short explanation, required if feasible=false, else null",
  "tables_used": ["table1", "table2"],
  "columns_used": ["table1.col", "table2.col"],
  "operation_type": "aggregation | filter | join | group_by | subquery | window | other",
  "sql": "the query, or null if not feasible"
}

HARD RULES - violating any of these makes the query invalid:
1. Only reference tables and columns that exist in the schemas provided. Never invent one.
2. Every non-aggregated column in a SELECT that also contains an aggregate function
   (COUNT, SUM, AVG, MIN, MAX) MUST appear in a GROUP BY clause. If the user's request
   mixes an aggregate total with a per-row detail that can't logically coexist in one
   query, set feasible=false and explain the conflict, OR split the intent and pick the
   single most likely correct interpretation - never emit invalid SQL to satisfy both.
3. For JOINs: only join on columns that plausibly correspond across tables (matching
   names/types). If no clear join key exists between the requested tables, set
   feasible=false with the reason.
4. Use explicit JOIN syntax (INNER/LEFT/etc), never comma joins.
5. Always alias tables when more than one table is used, and qualify every column
   reference with its table alias to avoid ambiguity.
6. If the request is ambiguous (could reasonably mean two different queries), pick the
   most literal, common-sense interpretation and proceed - do not ask a question back.
7. Never use SELECT * in aggregate or join queries - always name columns explicitly.
8. Double-check your own SQL mentally before returning it: does every clause reference
   real columns, does GROUP BY cover all non-aggregated selected columns, are joins
   using ON with real matching keys? If any check fails, fix the SQL or set
   feasible=false - never return SQL you are not confident is syntactically valid.
9. This is a READ-ONLY tool. Never generate INSERT, UPDATE, DELETE, DROP, ALTER,
   TRUNCATE, CREATE, REPLACE, or any statement that mutates data or schema. If asked
   to, set feasible=false with reason "read-only tool".
"""


def plan_and_generate(schemas: dict, user_request: str) -> dict:
    """
    schemas: {"table_name": {"columns": [{"name": ..., "type": ...}, ...]}, ...}
              (pass a dict with more than one table to enable joins/cross-table SQL)
    user_request: plain-English request from the user

    Returns dict matching the JSON shape in SYSTEM_PROMPT.
    On any parsing/response failure, returns a safe feasible=false result
    instead of raising, so the pipeline never crashes on a bad LLM response.
    """
    user_prompt = f"""Table schemas: {json.dumps(schemas)}
User request: {user_request}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            return _fallback("LLM returned an empty response, please retry.")
        raw = content.strip()
    except Exception as e:
        return _fallback(f"LLM request failed: {e}")

    # strip accidental code fences if the model adds them anyway
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback("LLM returned invalid JSON, please retry.")

    # enforce required keys exist, fill in safe defaults if missing
    parsed.setdefault("feasible", False)
    parsed.setdefault("reason", None)
    parsed.setdefault("tables_used", [])
    parsed.setdefault("columns_used", [])
    parsed.setdefault("operation_type", None)
    parsed.setdefault("sql", None)

    # Safety net: block any mutating statement even if the LLM ignored the rule.
    # Uses a WORD-BOUNDARY regex, not plain substring matching, so a real
    # column like "updated_at" or "inserted_by" is no longer falsely blocked
    # just because it contains the letters of a blocked keyword.
    if parsed.get("sql"):
        upper_sql = parsed["sql"].upper()
        for keyword in BLOCKED_KEYWORDS:
            if re.search(rf"\b{keyword}\b", upper_sql):
                return _fallback(f"Blocked unsafe SQL containing {keyword}.")

    return parsed


def _fallback(reason: str) -> dict:
    return {
        "feasible": False,
        "reason": reason,
        "tables_used": [],
        "columns_used": [],
        "operation_type": None,
        "sql": None,
    }