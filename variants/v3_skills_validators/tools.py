"""
Domain tools for variant 3. Each one does a whole calculation the definitions describe, so
the model picks the tool and the inputs, and the code does the arithmetic.

Every tool result says "missing_data": true when the inputs it needs are absent. The
validator uses that flag to force an abstention.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import json
import math

from variants.common import connect_ro

ACTUAL_WEEKS = (0, 1, 2)
TODAY = "2026-11-16"


def _q(sql, args=()):
    con = connect_ro()
    try:
        cur = con.execute(sql, args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def _brand(brand_id):
    r = _q("select * from brands where brand_id = ?", (brand_id,))
    if not r:
        raise ValueError(f"unknown brand_id {brand_id!r}; call portfolio or check_coverage for valid ids")
    return r[0]


def _week_index(week_start):
    r = _q("select week_index from weeks where week_start = ?", (week_start,))
    if not r:
        raise ValueError(f"{week_start!r} is not a week_start (Mondays from 2026-10-26 to 2027-01-18)")
    return r[0]["week_index"]


def _r(x):
    return None if x is None else round(float(x), 2)


# ------------------------------------------------------------------------------------------- tools
def check_coverage(brand_id):
    rows = _q("select source, status, last_week_with_actuals, note from data_coverage where brand_id = ?", (brand_id,))
    gaps = [r for r in rows if r["status"] != "connected" or r["note"]]
    return {"brand_id": brand_id, "sources": rows, "gaps": gaps,
            "note": "A gap only matters if the question needs that source or week."}


def cash_path(brand_id, basis="forecast", from_week_start=None):
    b = _brand(brand_id)
    rows = _q("select week_index, week_start, sum(forecast) f, sum(actual) a, count(actual) na, count(*) n "
              "from weekly_cash where brand_id = ? and is_cash = 1 group by week_index order by week_index", (brand_id,))
    flows = []
    for r in rows:
        if basis == "rollforward" and r["week_index"] in ACTUAL_WEEKS:
            if r["na"] != r["n"]:
                return {"brand_id": brand_id, "basis": basis, "missing_data": True,
                        "detail": f"actuals missing for the week of {r['week_start']}; roll-forward not possible"}
            flows.append(r["a"])
        elif basis in ("forecast", "rollforward"):
            flows.append(r["f"])
        else:
            raise ValueError("basis must be 'forecast' or 'rollforward'")
    closing, c = [], b["opening_cash"]
    for r, fl in zip(rows, flows):
        c += fl
        closing.append({"week_start": r["week_start"], "net_flow": _r(fl), "closing_cash": _r(c)})
    start = _week_index(from_week_start) if from_week_start else (3 if basis == "rollforward" else 0)
    window = [x for x, r in zip(closing, rows) if r["week_index"] >= start]
    low = min(window, key=lambda x: x["closing_cash"])
    gap = max(0.0, b["cash_buffer"] - low["closing_cash"])
    return {"brand_id": brand_id, "basis": basis, "missing_data": False, "opening_cash": b["opening_cash"],
            "cash_buffer": b["cash_buffer"], "weeks": closing, "low_point_from": window[0]["week_start"],
            "low_point": low["closing_cash"], "low_point_week": low["week_start"], "gap_to_buffer": _r(gap),
            "draw_to_hold_buffer": math.ceil(gap / 25000) * 25000,
            "low_point_to_buffer_ratio": _r(low["closing_cash"] / b["cash_buffer"]),
            "ending_cash": closing[-1]["closing_cash"]}


def variance(brand_id, line="all", from_week_start="2026-10-26", to_week_start="2026-11-09"):
    _brand(brand_id)
    a, z = _week_index(from_week_start), _week_index(to_week_start)
    if z > max(ACTUAL_WEEKS):
        return {"missing_data": True, "detail": "actuals run only through the week of 2026-11-09"}
    sql = ("select line, sum(actual - forecast) v, count(actual) na, count(*) n from weekly_cash "
           "where brand_id = ? and is_cash = 1 and week_index between ? and ?")
    args = [brand_id, a, z]
    if line != "all":
        sql += " and line = ?"
        args.append(line)
    rows = _q(sql + " group by line", args)
    if not rows:
        raise ValueError(f"no cash line {line!r}")
    if any(r["na"] != r["n"] for r in rows):
        return {"brand_id": brand_id, "missing_data": True, "detail": "some actuals in that range are missing"}
    by_line = {r["line"]: _r(r["v"]) for r in rows}
    return {"brand_id": brand_id, "line": line, "from": from_week_start, "to": to_week_start, "missing_data": False,
            "variance_actual_minus_forecast": _r(sum(r["v"] for r in rows)), "by_line": by_line}


def driver_variance(brand_id, kind, from_week_start="2026-10-26", to_week_start="2026-11-09"):
    _brand(brand_id)
    if kind not in ("refunds_by_sku", "ad_spend"):
        raise ValueError("kind must be 'refunds_by_sku' or 'ad_spend'")
    key = "sku" if kind == "refunds_by_sku" else "platform"
    a, z = _week_index(from_week_start), _week_index(to_week_start)
    rows = _q(f"select {key} k, sum(actual - forecast) v, sum(actual) act, sum(forecast) fc, count(actual) na, "
              f"count(*) n from {kind} where brand_id = ? and week_index between ? and ? group by {key}",
              (brand_id, a, z))
    if not rows:
        return {"brand_id": brand_id, "kind": kind, "missing_data": True,
                "detail": f"no {kind} data for this brand (see check_coverage)"}
    if any(r["na"] != r["n"] for r in rows):
        return {"brand_id": brand_id, "kind": kind, "missing_data": True, "detail": "actuals missing in that range"}
    items = sorted(({key: r["k"], "variance_actual_minus_forecast": _r(r["v"]), "actual": _r(r["act"]),
                     "forecast": _r(r["fc"])} for r in rows), key=lambda x: -x["variance_actual_minus_forecast"])
    return {"brand_id": brand_id, "kind": kind, "missing_data": False, "items": items,
            "largest_overrun": items[0][key], "largest_overrun_amount": items[0]["variance_actual_minus_forecast"]}


def week_lines(brand_id, week_start, basis="forecast"):
    _brand(brand_id)
    w = _week_index(week_start)
    col = "actual" if basis == "actual" else "forecast"
    rows = _q(f"select line, is_cash, {col} v from weekly_cash where brand_id = ? and week_index = ?", (brand_id, w))
    if any(r["v"] is None for r in rows):
        return {"brand_id": brand_id, "week_start": week_start, "basis": basis, "missing_data": True,
                "detail": "no actuals for that week"}
    cash = [r for r in rows if r["is_cash"] == 1]
    return {"brand_id": brand_id, "week_start": week_start, "basis": basis, "missing_data": False,
            "lines": {r["line"]: _r(r["v"]) for r in rows},
            "cash_in": _r(sum(r["v"] for r in cash if r["v"] > 0)),
            "cash_out_positive": _r(-sum(r["v"] for r in cash if r["v"] < 0)),
            "net": _r(sum(r["v"] for r in cash))}


def line_series(brand_id, line, basis="forecast"):
    _brand(brand_id)
    col = "actual" if basis == "actual" else "forecast"
    rows = _q(f"select week_start, {col} v from weekly_cash where brand_id = ? and line = ? order by week_index",
              (brand_id, line))
    if not rows:
        raise ValueError(f"no line {line!r}")
    vals = [r["v"] for r in rows if r["v"] is not None]
    return {"brand_id": brand_id, "line": line, "basis": basis, "missing_data": basis == "actual" and len(vals) < 3,
            "weeks": {r["week_start"]: _r(r["v"]) for r in rows}, "total": _r(sum(vals)),
            "weeks_with_payment": sum(1 for v in vals if abs(v) > 0)}


def bills(brand_id, bill_id=None, due_week_start=None):
    _brand(brand_id)
    cov = _q("select status from data_coverage where brand_id = ? and source = 'ap_bills'", (brand_id,))
    if cov and cov[0]["status"] != "connected":
        return {"brand_id": brand_id, "missing_data": True, "detail": "AP bills are not connected for this brand"}
    sql, args = "select * from bills where brand_id = ?", [brand_id]
    if bill_id:
        sql += " and bill_id = ?"
        args.append(bill_id)
    if due_week_start:
        sql += " and due_week_start = ?"
        args.append(due_week_start)
    rows = _q(sql + " order by amount desc", args)
    for r in rows:
        r["discount_amount"] = _r(r["amount"] * (r["discount_pct"] or 0))
    return {"brand_id": brand_id, "missing_data": False, "bills": rows,
            "largest": rows[0]["bill_id"] if rows else None}


def credit_math(brand_id, op, amount=None, weeks=None, gap=None):
    b = _brand(brand_id)
    if op == "interest":
        return {"op": op, "amount": amount, "weeks": weeks, "apr": b["loc_apr"],
                "interest": _r(amount * b["loc_apr"] * weeks / 52)}
    if op == "draw_for_gap":
        return {"op": op, "gap": gap, "draw": math.ceil(max(0.0, gap) / 25000) * 25000}
    if op == "paydown_vs_sweep":
        amt = b["loc_drawn"] if amount is None else amount
        return {"op": op, "amount": amt, "apr": b["loc_apr"], "savings_apy": b["savings_apy"],
                "annual_benefit_of_paydown": _r(amt * (b["loc_apr"] - b["savings_apy"]))}
    raise ValueError("op must be interest, draw_for_gap or paydown_vs_sweep")


def portfolio(metric, line=None):
    brands = [r["brand_id"] for r in _q("select brand_id from brands order by brand_id")]
    if metric == "low_point_vs_buffer":
        rows = []
        for b in brands:
            c = cash_path(b, "forecast")
            rows.append({"brand_id": b, "low_point": c["low_point"], "cash_buffer": c["cash_buffer"],
                         "ratio": c["low_point_to_buffer_ratio"], "below_buffer": c["low_point"] < c["cash_buffer"]})
        return {"metric": metric, "brands": rows, "count_below_buffer": sum(r["below_buffer"] for r in rows),
                "lowest_ratio_brand": min(rows, key=lambda r: r["ratio"])["brand_id"]}
    if metric == "brands_without_line":
        rows = _q("select brand_id, sum(abs(forecast)) s from weekly_cash where line = ? group by brand_id", (line,))
        return {"metric": metric, "line": line, "brands": sorted(r["brand_id"] for r in rows if not r["s"])}
    raise ValueError("metric must be low_point_vs_buffer or brands_without_line")


S = lambda props, req: {"type": "object", "properties": props, "required": req}
STR = {"type": "string"}
NUMBER = {"type": "number"}
TOOLS = [
    {"name": "load_skill", "description": "Read a skill's instructions (SKILL.md). Do this before using its tools.",
     "input_schema": S({"name": STR}, ["name"])},
    {"name": "check_coverage", "description": "Which data sources are connected for a brand and which weeks arrived.",
     "input_schema": S({"brand_id": STR}, ["brand_id"])},
    {"name": "cash_path", "description": "Closing cash by week, low point, its week, gap to buffer and draw to hold "
                                         "the buffer. basis: forecast or rollforward.",
     "input_schema": S({"brand_id": STR, "basis": STR, "from_week_start": STR}, ["brand_id", "basis"])},
    {"name": "variance", "description": "Actual minus forecast for one cash line or 'all', over a week range "
                                        "(week_start dates, inclusive).",
     "input_schema": S({"brand_id": STR, "line": STR, "from_week_start": STR, "to_week_start": STR},
                       ["brand_id", "line"])},
    {"name": "driver_variance", "description": "Actual minus forecast by SKU (kind=refunds_by_sku) or by ad platform "
                                               "(kind=ad_spend), largest overrun first.",
     "input_schema": S({"brand_id": STR, "kind": STR, "from_week_start": STR, "to_week_start": STR},
                       ["brand_id", "kind"])},
    {"name": "week_lines", "description": "Every line for one week, with cash in, cash out (positive) and net. "
                                          "basis: forecast or actual.",
     "input_schema": S({"brand_id": STR, "week_start": STR, "basis": STR}, ["brand_id", "week_start"])},
    {"name": "line_series", "description": "One line across all 13 weeks, its total and the number of weeks with a "
                                           "payment. basis: forecast or actual.",
     "input_schema": S({"brand_id": STR, "line": STR, "basis": STR}, ["brand_id", "line"])},
    {"name": "bills", "description": "AP bills for a brand, optionally one bill_id or bills due in one week, largest "
                                     "first, with the early-pay discount in dollars.",
     "input_schema": S({"brand_id": STR, "bill_id": STR, "due_week_start": STR}, ["brand_id"])},
    {"name": "credit_math", "description": "op=interest (amount, weeks), op=draw_for_gap (gap), op=paydown_vs_sweep "
                                           "(amount, defaults to the drawn balance). Uses the brand's rates.",
     "input_schema": S({"brand_id": STR, "op": STR, "amount": NUMBER, "weeks": NUMBER, "gap": NUMBER},
                       ["brand_id", "op"])},
    {"name": "portfolio", "description": "Across all brands: metric=low_point_vs_buffer, or metric=brands_without_line "
                                         "with line.",
     "input_schema": S({"metric": STR, "line": STR}, ["metric"])},
]

IMPL = {"check_coverage": check_coverage, "cash_path": cash_path, "variance": variance,
        "driver_variance": driver_variance, "week_lines": week_lines, "line_series": line_series, "bills": bills,
        "credit_math": credit_math, "portfolio": portfolio}


def call(name, args):
    try:
        return json.dumps(IMPL[name](**args), default=str)
    except (TypeError, ValueError) as e:
        return json.dumps({"error": str(e)})
