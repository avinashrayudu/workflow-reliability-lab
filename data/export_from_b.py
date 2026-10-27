"""
Exports the data the Cash Brief workflow reads, from a forecast-health-monitor checkout.

  python -m data.export_from_b ../forecast-health-monitor

Writes data/csv/*.csv and data/portfolio.sqlite. The committed copies were made this
way, so the lab runs without the other repository. The snapshot is Monday Nov 16, 2026:
actuals through Sunday Nov 15 (weeks 0-2), forecast for every week from Oct 26.

Three gaps are cut on purpose, so the eval can test whether a workflow says
"I can't answer that" instead of guessing:
  copperleaf-tea      no actuals for the week of Nov 9 (that upload never arrived)
  saltmarsh-apparel   no AP bills (the bill-pay export is not connected)
  lark-and-pine       no refunds by SKU (only payout totals are connected)

Built by Avinash Rayudu. All brands and numbers are synthetic.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "csv"
DB = ROOT / "data" / "portfolio.sqlite"
ACTUAL_THROUGH = 2          # week index of the last week with actuals (Nov 9-15)

GAPS = {"copperleaf-tea": "missing_week", "saltmarsh-apparel": "no_bills", "lark-and-pine": "no_sku_refunds"}

SCHEMA = {
    "brands": ["brand_id", "brand", "currency", "opening_cash", "cash_buffer", "loc_limit", "loc_drawn", "loc_apr",
               "savings_apy", "materiality"],
    "weeks": ["week_index", "week_start", "has_actuals"],
    "weekly_cash": ["brand_id", "week_index", "week_start", "line", "is_cash", "forecast", "actual"],
    "refunds_by_sku": ["brand_id", "week_index", "week_start", "sku", "forecast", "actual"],
    "ad_spend": ["brand_id", "week_index", "week_start", "platform", "forecast", "actual"],
    "bills": ["brand_id", "bill_id", "vendor", "line", "currency", "amount", "issue_week_start", "due_week_start",
              "discount_pct", "discount_deadline_week_start", "criticality"],
    "data_coverage": ["brand_id", "source", "status", "last_week_with_actuals", "note"],
}


def r2(x):
    return None if x is None else round(float(x), 2)


def export(b_root: Path):
    sys.path.insert(0, str(b_root))
    from world.engine import CASH_LINES, N_WEEKS, WATCH_LINES, WEEKS
    from world.inject_events import DEV_EVENTS, build_scenario, load_configs

    cfgs = load_configs()
    books = build_scenario(cfgs, DEV_EVENTS, "dev")
    ws = lambda w: WEEKS[w].isoformat() if 0 <= w < N_WEEKS else None
    rows = {k: [] for k in SCHEMA}
    for w in range(N_WEEKS):
        rows["weeks"].append([w, ws(w), int(w <= ACTUAL_THROUGH)])
    for slug, b in books.items():
        cfg, fc, act = cfgs[slug], b["forecast"], b["actual"]
        gap = GAPS.get(slug)
        rows["brands"].append([slug, cfg["brand"], cfg["currency"], r2(cfg["opening_cash"]), r2(cfg["cash_buffer"]),
                               r2(cfg["loc_limit"]), r2(cfg["loc_drawn"]), cfg["loc_apr"], cfg["savings_apy"],
                               r2(cfg["materiality"])])
        has = lambda w: w <= ACTUAL_THROUGH and not (gap == "missing_week" and w == ACTUAL_THROUGH)
        for line in CASH_LINES + WATCH_LINES:
            for w in range(N_WEEKS):
                rows["weekly_cash"].append([slug, w, ws(w), line, int(line in CASH_LINES), r2(fc.lines[line][w]),
                                            r2(act.lines[line][w]) if has(w) else None])
        if gap != "no_sku_refunds":
            for sku in fc.drivers["dtc_refunds_by_sku"]:
                for w in range(N_WEEKS):
                    rows["refunds_by_sku"].append([slug, w, ws(w), sku, r2(fc.drivers["dtc_refunds_by_sku"][sku][w]),
                                                   r2(act.drivers["dtc_refunds_by_sku"][sku][w]) if has(w) else None])
        for p in fc.drivers["ad_by_platform"]:
            for w in range(N_WEEKS):
                rows["ad_spend"].append([slug, w, ws(w), p, r2(fc.drivers["ad_by_platform"][p][w]),
                                         r2(act.drivers["ad_by_platform"][p][w]) if has(w) else None])
        if gap != "no_bills":
            for bl in fc.bills:
                dl = bl["issue_week"] + bl["discount_weeks"] if bl["discount_pct"] > 0 else None
                rows["bills"].append([slug, bl["id"], bl["vendor"], bl["line"], bl["currency"], r2(bl["amount"]),
                                      ws(bl["issue_week"]) or f"before {ws(0)}", ws(bl["due_week"]) or "after window",
                                      bl["discount_pct"], ws(dl) if dl is not None else None, bl["criticality"]])
        last = ws(ACTUAL_THROUGH - 1 if gap == "missing_week" else ACTUAL_THROUGH)
        for src in ("bank", "shopify", "amazon", "card", "wholesale", "ap_bills", "sku_refunds"):
            status, through, note = "connected", last, ""
            if gap == "missing_week" and src in ("bank", "shopify", "amazon", "card", "wholesale", "sku_refunds"):
                note = "upload for the week of Nov 9 not received"
            if gap == "no_bills" and src == "ap_bills":
                status, through, note = "not connected", None, "bill-pay export not set up"
            if gap == "no_sku_refunds" and src == "sku_refunds":
                status, through, note = "not connected", None, "only payout totals are connected"
            if src == "ap_bills" and status == "connected":
                through, note = None, "open and scheduled bills, all known as of Nov 16"
            rows["data_coverage"].append([slug, src, status, through, note])
    CSV.mkdir(parents=True, exist_ok=True)
    for name, cols in SCHEMA.items():
        with open(CSV / f"{name}.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(cols)
            wr.writerows(rows[name])
    build_db()
    print(f"exported {sum(len(v) for v in rows.values())} rows to data/csv and {DB.relative_to(ROOT)}")


def build_db(path: Path = DB):
    """(Re)build the SQLite file from the CSVs."""
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    for name in SCHEMA:
        with open(CSV / f"{name}.csv") as f:
            rd = csv.reader(f)
            cols = next(rd)
            con.execute(f"create table {name} ({', '.join(cols)})")
            data = [[None if v == "" else _num(v) for v in r] for r in rd]
            con.executemany(f"insert into {name} values ({', '.join('?' * len(cols))})", data)
    con.commit()
    con.close()


def _num(v):
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


if __name__ == "__main__":
    if len(sys.argv) > 1:
        export(Path(sys.argv[1]).resolve())
    else:
        build_db()
        print(f"rebuilt {DB.relative_to(ROOT)} from data/csv")
