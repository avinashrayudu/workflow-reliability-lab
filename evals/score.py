"""
Exact-answer scoring.

Each answer gets one outcome: correct, wrong_number, wrong_date, wrong_entity, wrong_count,
wrong_set, missed_abstention, false_abstention or format_error.

  money   correct within max($1, 0.05%); numeric error = |answer - truth| / |truth|
  date    the same Monday (YYYY-MM-DD, or a written date that parses)
  text    case-insensitive match; a brand may be given by brand_id or name
  int     exact
  set     the same items, order ignored
  abstain correct only if the answer abstains

On an answerable question, abstaining counts as false_abstention.

The brief is scored field by field. Every dollar figure in its narrative must also match
a Fernwood number from the data or the truth file within 0.5%; anything else counts as
an unsupported number.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

import yaml

from variants.common import dollar_figures, supported

ROOT = Path(__file__).resolve().parent.parent
TRUTH = json.loads((ROOT / "truth" / "answers.json").read_text())
QS = yaml.safe_load((ROOT / "truth" / "questions.yaml").read_text())
QTYPE = {q["id"]: q["type"] for q in QS["questions"]}
QBRAND = {q["id"]: q["brand"] for q in QS["questions"]} | {"B01": QS["brief"]["brand"]}
BRIEF_FIELDS = QS["brief"]["fields"]
with open(ROOT / "data" / "csv" / "brands.csv") as f:
    NAME_TO_ID = {r["brand"].lower(): r["brand_id"] for r in csv.DictReader(f)}


def _money(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    try:
        x = float(s.strip("()"))
    except ValueError:
        m = re.search(r"-?\d+\.?\d*", s)
        if not m:
            return None
        x = float(m.group())
    return -x if neg else x


def _date(v):
    if not isinstance(v, str):
        return None
    s = v.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    return m.group() if m else None


def _text(v):
    if v is None:
        return None
    s = str(v).strip().strip("'\"").lower()
    return NAME_TO_ID.get(s, s)


def normalize(qtype, value):
    if qtype == "money":
        x = _money(value)
        return None if x is None else round(x, 2)
    if qtype == "date":
        return _date(value)
    if qtype == "text":
        return _text(value)
    if qtype == "int":
        x = _money(value)
        return None if x is None else int(round(x))
    if qtype == "set":
        items = value if isinstance(value, list) else re.split(r"[,;]\s*", str(value or ""))
        return tuple(sorted(_text(i) for i in items if str(i).strip()))
    return value


def check(qtype, expected, value):
    """(outcome, numeric_error) for one answerable value."""
    got = normalize(qtype, value)
    if got is None:
        return "format_error", None
    if qtype == "money":
        err = abs(got - expected) / max(abs(expected), 1.0)
        ok = abs(got - expected) <= max(1.0, 0.0005 * abs(expected))
        return ("correct" if ok else "wrong_number"), err
    if qtype == "date":
        return ("correct" if got == expected else "wrong_date"), None
    if qtype == "text":
        return ("correct" if got == _text(expected) else "wrong_entity"), None
    if qtype == "int":
        return ("correct" if got == expected else "wrong_count"), abs(got - expected) / max(abs(expected), 1)
    if qtype == "set":
        return ("correct" if got == tuple(sorted(expected)) else "wrong_set"), None
    raise ValueError(qtype)


def score_question(qid, parsed):
    qt = QTYPE[qid]
    exp = TRUTH["answers"][qid]
    if parsed is None or not isinstance(parsed, dict):
        return {"outcome": "format_error", "correct": False, "numeric_error": None, "norm": "FORMAT"}
    abstained = bool(parsed.get("abstain")) or ("answer" in parsed and parsed.get("answer") is None)
    if qt == "abstain":
        oc = "correct" if abstained else "missed_abstention"
        return {"outcome": oc, "correct": oc == "correct", "numeric_error": None,
                "norm": "ABSTAIN" if abstained else str(parsed.get("answer"))}
    if abstained:
        return {"outcome": "false_abstention", "correct": False, "numeric_error": None, "norm": "ABSTAIN"}
    oc, err = check(qt, exp, parsed.get("answer"))
    return {"outcome": oc, "correct": oc == "correct", "numeric_error": err,
            "norm": str(normalize(qt, parsed.get("answer")))}


def score_brief(parsed):
    exp = TRUTH["answers"]["B01"]
    if not isinstance(parsed, dict) or "narrative" not in parsed:
        return {"outcome": "format_error", "correct": False, "fields_correct": 0, "fields": len(BRIEF_FIELDS),
                "field_outcomes": {}, "dollar_figures": 0, "unsupported": 0, "numeric_error": None, "norm": "FORMAT"}
    outs, errs = {}, []
    for k, t in BRIEF_FIELDS.items():
        if parsed.get(k) is None:
            outs[k] = "false_abstention"
            continue
        oc, err = check(t, exp[k], parsed[k])
        outs[k] = oc
        if err is not None and t == "money":
            errs.append(err)
    allowed = TRUTH["brief_support"] + [abs(v) for v in exp.values() if isinstance(v, (int, float))]
    figs = dollar_figures(parsed.get("narrative"))
    unsup = [x for x in figs if not supported(x, allowed)]
    n_ok = sum(o == "correct" for o in outs.values())
    worst = next((o for o in outs.values() if o != "correct"), None)
    oc = "correct" if n_ok == len(outs) and not unsup else (worst or "unsupported_number")
    return {"outcome": oc, "correct": oc == "correct", "fields_correct": n_ok, "fields": len(outs),
            "field_outcomes": outs, "dollar_figures": len(figs), "unsupported": len(unsup),
            "unsupported_values": unsup, "numeric_error": max(errs) if errs else None,
            "norm": json.dumps({k: str(normalize(BRIEF_FIELDS[k], parsed.get(k))) for k in BRIEF_FIELDS},
                               sort_keys=True)}


def score(qid, parsed):
    return score_brief(parsed) if qid == "B01" else score_question(qid, parsed)
