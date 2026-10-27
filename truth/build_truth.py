"""
Computes the expected answer to every question from data/csv with pandas.

  python -m truth.build_truth          writes truth/answers.json and checks it against Project B

This is one of two independent computations of the answers. The other is the set of
reference SQL plans in evals/mock_plans.yaml. A test requires the two to agree on every
question. A third check compares the Fernwood figures with what forecast-health-monitor
itself printed: the $194,498 low point in the week of Nov 16 and the $125,000 draw.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "csv"
OUT = ROOT / "truth" / "answers.json"
TODAY_WEEK = 3
ACTUAL_WEEKS = [0, 1, 2]


def load():
    t = {n: pd.read_csv(CSV / f"{n}.csv") for n in ("brands", "weeks", "weekly_cash", "refunds_by_sku", "ad_spend",
                                                      "bills", "data_coverage")}
    return t


class Truth:
    def __init__(self):
        self.t = load()
        self.b = self.t["brands"].set_index("brand_id")
        self.wc = self.t["weekly_cash"]
        self.cash = self.wc[self.wc["is_cash"] == 1]
        self.week = dict(zip(self.t["weeks"]["week_index"], self.t["weeks"]["week_start"]))

    # ---------------------------------------------------------------- building blocks
    def flows(self, brand, basis="forecast"):
        c = self.cash[self.cash["brand_id"] == brand]
        f = c.groupby("week_index")["forecast"].sum()
        if basis == "forecast":
            return f
        a = c[c["week_index"].isin(ACTUAL_WEEKS)]
        if a["actual"].isna().any():
            return None
        act = a.groupby("week_index")["actual"].sum()
        return pd.concat([act, f[f.index > max(ACTUAL_WEEKS)]])

    def closing(self, brand, basis="forecast"):
        fl = self.flows(brand, basis)
        return None if fl is None else self.b.loc[brand, "opening_cash"] + fl.cumsum()

    def low(self, brand, basis="forecast", from_week=0):
        cl = self.closing(brand, basis)
        if cl is None:
            return None
        cl = cl[cl.index >= from_week]
        w = int(cl.idxmin())
        return float(cl.min()), self.week[w]

    def gap(self, brand, low):
        return max(0.0, float(self.b.loc[brand, "cash_buffer"]) - low)

    @staticmethod
    def draw(gap):
        return math.ceil(gap / 25000) * 25000

    def variance(self, brand, line=None, weeks=ACTUAL_WEEKS):
        c = self.cash[(self.cash["brand_id"] == brand) & self.cash["week_index"].isin(weeks)]
        if line:
            c = c[c["line"] == line]
        if c["actual"].isna().any():
            return None
        return float((c["actual"] - c["forecast"]).sum())

    def sku_overrun(self, brand):
        r = self.t["refunds_by_sku"]
        r = r[(r["brand_id"] == brand) & r["week_index"].isin(ACTUAL_WEEKS)]
        if r.empty or r["actual"].isna().any():
            return None
        return (r["actual"] - r["forecast"]).groupby(r["sku"]).sum()

    def line_at(self, brand, line, week, col="forecast"):
        c = self.wc
        v = c[(c["brand_id"] == brand) & (c["line"] == line) & (c["week_index"] == week)][col]
        return None if v.isna().any() else float(v.iloc[0])

    def bill(self, brand, bill_id):
        bl = self.t["bills"]
        r = bl[(bl["brand_id"] == brand) & (bl["bill_id"] == bill_id)]
        return None if r.empty else r.iloc[0]

    # ---------------------------------------------------------------- answers
    def answers(self):
        F = "fernwood-goods"
        A = {}
        low1, low1w = self.low(F)
        A["Q01"], A["Q02"] = low1, low1w
        A["Q03"] = self.gap(F, low1)
        A["Q04"] = float(self.draw(A["Q03"]))
        A["Q05"] = float(self.closing(F, "rollforward").loc[2])
        A["Q06"] = self.variance(F, "dtc_payouts")
        ov = self.sku_overrun(F)
        A["Q07"] = str(ov.idxmax())
        A["Q08"] = float(ov.loc["FW-2201"])
        bl = self.t["bills"]
        due = bl[(bl["brand_id"] == F) & (bl["due_week_start"] == self.week[TODAY_WEEK])]
        A["Q09"] = str(due.sort_values("amount", ascending=False).iloc[0]["bill_id"])
        wk = self.cash[(self.cash["brand_id"] == F) & (self.cash["week_index"] == TODAY_WEEK)]
        A["Q10"] = float(-wk.loc[wk["forecast"] < 0, "forecast"].sum())
        A["Q11"] = -self.line_at(F, "card_autopay", TODAY_WEEK)
        tpl = self.bill(F, "TPL-202611")
        A["Q12"] = float(tpl["amount"] * tpl["discount_pct"])
        A["Q13"] = str(tpl["discount_deadline_week_start"])
        A["Q14"] = 125000 * float(self.b.loc[F, "loc_apr"]) / 52
        A["Q15"] = float(self.b.loc[F, "loc_drawn"] * (self.b.loc[F, "loc_apr"] - self.b.loc[F, "savings_apy"]))
        A["Q16"] = self.low(F, "rollforward", TODAY_WEEK)[0]
        A["Q17"] = self.variance(F)
        A["Q18"] = self.variance("hollis-home", "freight_duty", [2])
        ratios = {b: self.low(b)[0] / float(self.b.loc[b, "cash_buffer"]) for b in self.b.index}
        A["Q19"] = sum(r < 1 for r in ratios.values())
        A["Q20"] = min(ratios, key=ratios.get)
        wr = self.cash[self.cash["line"] == "wholesale_receipts"].groupby("brand_id")["forecast"].apply(
            lambda s: (s.abs() > 0).any())
        A["Q21"] = sorted(b for b, has in wr.items() if not has)
        ad = self.t["ad_spend"]
        ad = ad[(ad["brand_id"] == "north-arc-outdoor") & (ad["platform"] == "meta") & ad["week_index"].isin(ACTUAL_WEEKS)]
        A["Q22"] = float((ad["actual"] - ad["forecast"]).sum())
        A["Q23"] = self.line_at("tidewater-swim", "marketplace_payouts", 2, "actual")
        q = self.cash[(self.cash["brand_id"] == "quillon-coffee") & (self.cash["line"] == "wholesale_receipts")]
        A["Q24"] = float(q["forecast"].sum())
        p = self.cash[(self.cash["brand_id"] == "bramble-pet") & (self.cash["line"] == "payroll")]
        A["Q25"] = int((p["forecast"] != 0).sum())
        A["Q26"] = -self.line_at("marigold-skin", "sales_tax", TODAY_WEEK)
        A["Q27"] = float(self.closing(F).iloc[-1])
        # abstentions: each must be unanswerable from the data, which these checks confirm
        assert self.line_at("copperleaf-tea", "dtc_payouts", 2, "actual") is None
        assert self.variance("copperleaf-tea") is None
        assert self.bill("saltmarsh-apparel", "PO-SPRING-DEP") is None
        assert self.sku_overrun("lark-and-pine") is None
        for k in ("Q28", "Q29", "Q30", "Q31"):
            A[k] = "ABSTAIN"
        A["Q32"] = self.variance("lark-and-pine", "dtc_payouts")
        A["Q33"] = self.low("saltmarsh-apparel")[0]
        # the brief
        low, loww = self.low(F, "rollforward", TODAY_WEEK)
        g = self.gap(F, low)
        d = self.draw(g)
        A["B01"] = dict(low_point=low, low_point_week=loww, gap_to_buffer=g, draw=float(d),
                        interest_one_week=d * float(self.b.loc[F, "loc_apr"]) / 52, top_refund_sku=A["Q07"],
                        payout_variance=A["Q06"], largest_bill_this_week=A["Q09"])
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in A.items()} | {
            "B01": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in A["B01"].items()}}

    def brief_support(self):
        """Dollar figures a Fernwood brief may cite: every Fernwood number in the data, the
        answers, and the simple sums the definitions describe."""
        F = "fernwood-goods"
        vals = set()
        for name in ("weekly_cash", "refunds_by_sku", "ad_spend", "bills"):
            df = self.t[name]
            df = df[df["brand_id"] == F]
            for c in ("forecast", "actual", "amount"):
                if c in df:
                    vals |= {round(abs(float(x)), 2) for x in df[c].dropna()}
        for c in ("opening_cash", "cash_buffer", "loc_limit", "loc_drawn", "materiality"):
            vals.add(float(self.b.loc[F, c]))
        vals.add(float(self.b.loc[F, "loc_limit"] - self.b.loc[F, "loc_drawn"]))
        for basis in ("forecast", "rollforward"):
            vals |= {round(abs(float(x)), 2) for x in self.closing(F, basis)}
            vals |= {round(abs(float(x)), 2) for x in self.flows(F, basis)}
        for line in self.cash["line"].unique():
            v = self.variance(F, line)
            if v is not None:
                vals.add(round(abs(v), 2))
        vals |= {round(abs(float(x)), 2) for x in self.sku_overrun(F)}
        return sorted(vals)


def main():
    T = Truth()
    A = T.answers()
    qs = yaml.safe_load((ROOT / "truth" / "questions.yaml").read_text())
    ids = [q["id"] for q in qs["questions"]] + [qs["brief"]["id"]]
    assert set(ids) == set(A), set(ids) ^ set(A)
    # Project B printed these for the same data; the truth must reproduce them
    assert round(A["Q01"]) == 194498 and A["Q02"] == "2026-11-16" and A["Q04"] == 125000.0
    OUT.write_text(json.dumps({"answers": A, "brief_support": T.brief_support()}, indent=1))
    for k in ids:
        print(f"  {k}: {A[k]}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
