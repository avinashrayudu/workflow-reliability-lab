"""
Variant 1: one prompt.

Every table goes into the prompt as CSV, followed by the question. There are no
tools, so the model reads, adds up and answers in one pass. This is the
"paste the export into the chat" baseline.

Built by Avinash Rayudu.
"""
from __future__ import annotations

from variants.common import CSV, DEFINITIONS, TABLES

NAME = "v1_single_prompt"
MAX_TURNS = 1


def data_pack() -> str:
    parts = ["# Data (all tables, CSV)"]
    for t in TABLES:
        parts.append(f"### table: {t}\n```csv\n{(CSV / f'{t}.csv').read_text().strip()}\n```")
    return "\n\n".join(parts)


_PACK = None


def build(question: str):
    global _PACK
    if _PACK is None:
        _PACK = data_pack()
    system = (DEFINITIONS + "\n\nYou have no tools. Work from the tables below. Show brief working, then the "
              "final JSON line.\n\n" + _PACK)
    return dict(system=system, user=question, tools=[], tool_impl={}, validator=None, max_turns=MAX_TURNS)
