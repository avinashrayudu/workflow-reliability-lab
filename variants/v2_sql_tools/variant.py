"""
Variant 2: read-only SQL.

The model gets the schema and one tool, run_sql, over a read-only SQLite copy of
the same tables. It writes its own queries, so the arithmetic happens in the
database instead of in the model's head.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import json
import re
import sqlite3

from variants.common import DEFINITIONS, connect_ro, schema_text

NAME = "v2_sql_tools"
MAX_TURNS = 12
ROW_LIMIT = 200

TOOLS = [{
    "name": "run_sql",
    "description": ("Run one read-only SQLite query (SELECT or WITH ... SELECT) against the brand tables. "
                    f"Returns columns and up to {ROW_LIMIT} rows as JSON. NULL means the value is missing."),
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
}]


def run_sql(query: str) -> str:
    q = query.strip().rstrip(";")
    if not re.match(r"(?is)^\s*(select|with)\b", q) or ";" in q:
        return json.dumps({"error": "only a single SELECT or WITH query is allowed"})
    con = connect_ro()
    try:
        cur = con.execute(q)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(ROW_LIMIT + 1)
        return json.dumps({"columns": cols, "rows": [list(r) for r in rows[:ROW_LIMIT]],
                           "row_count": min(len(rows), ROW_LIMIT), "truncated": len(rows) > ROW_LIMIT})
    except sqlite3.Error as e:
        return json.dumps({"error": str(e)})
    finally:
        con.close()


def build(question: str):
    system = (DEFINITIONS + "\n\n# Tables (SQLite)\n" + schema_text() +
              "\n\nUse run_sql to look things up and do the arithmetic in SQL. SQLite supports window functions. "
              "Then give the final JSON line.")
    return dict(system=system, user=question, tools=TOOLS, tool_impl={"run_sql": lambda a: run_sql(a["query"])},
                validator=None, max_turns=MAX_TURNS)
