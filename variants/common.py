"""
Pieces every variant shares: the definitions, the data paths and the final-answer parser.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "portfolio.sqlite"
CSV = ROOT / "data" / "csv"
DEFINITIONS = (ROOT / "config" / "definitions.md").read_text()
TABLES = ["brands", "weeks", "weekly_cash", "refunds_by_sku", "ad_spend", "bills", "data_coverage"]


def connect_ro():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def schema_text():
    con = connect_ro()
    out = []
    for t in TABLES:
        cols = [r[1] for r in con.execute(f"pragma table_info({t})")]
        n = con.execute(f"select count(*) from {t}").fetchone()[0]
        out.append(f"- {t} ({n} rows): {', '.join(cols)}")
    con.close()
    return "\n".join(out)


def parse_final(text: str):
    """The last JSON object in the text that has an "abstain" or "answer" key."""
    if not text:
        return None
    cands = []
    for m in re.finditer(r"\{", text):
        depth = 0
        for j in range(m.start(), len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    cands.append(text[m.start():j + 1])
                    break
    for c in reversed(cands):
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("answer" in obj or "abstain" in obj or "low_point" in obj):
            return obj
    return None


NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def numbers_in(obj) -> list:
    """Every number in a JSON-like object or string."""
    out = []
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        for m in NUM.findall(obj):
            try:
                out.append(float(m.replace(",", "")))
            except ValueError:
                pass
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            out += numbers_in(v)
    if isinstance(obj, (list, tuple)):
        for v in obj:
            out += numbers_in(v)
    return out


DOLLAR = re.compile(r"\$\s?(\d[\d,]*\.?\d*)\s?([KkMm])?\b")


def dollar_figures(text: str) -> list:
    """Dollar amounts written in prose: $1,384.22, $186,241, $114K, $1.1M."""
    out = []
    for num, suf in DOLLAR.findall(text or ""):
        v = float(num.replace(",", ""))
        out.append(v * (1000 if suf in "Kk" and suf else 1_000_000 if suf in "Mm" and suf else 1))
    return out


def supported(value: float, allowed, rel=0.005, abs_tol=1.0) -> bool:
    """True when a cited figure matches an allowed figure, allowing for rounding in prose."""
    return any(abs(abs(value) - abs(a)) <= max(abs_tol, rel * abs(a)) for a in allowed)
