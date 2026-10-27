"""
Builds reports/reliability.html from evals/results/*/summary.json and runs.jsonl.

Each run gets its own section, under a banner that says what kind of run it was. Mock runs
are never mixed with live runs. A section has the variant scorecard, a question-by-question
grid (how many of the N runs were right) and the failure taxonomy by brand.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "evals" / "results"
OUT = ROOT / "reports" / "reliability.html"
QS = yaml.safe_load((ROOT / "truth" / "questions.yaml").read_text())
QTEXT = {q["id"]: q["q"] for q in QS["questions"]} | {"B01": "Fernwood Cash Brief (8 fields + cited figures)"}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1c1d1f;--muted:#5d6168;--line:#e3e3df;--ok:#2e7d4f;--ok-bg:#e8f4ec;
--bad:#b3261e;--bad-bg:#fbeceb;--mid:#9a6700;--mid-bg:#fdf3dc;--accent:#2f5d8a;--warn-bg:#fff6d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141517;--card:#1d1f22;--ink:#ececea;
--muted:#a4a8ae;--line:#33363b;--ok:#7cc79a;--ok-bg:#1f3327;--bad:#f08a83;--bad-bg:#3a1f1e;--mid:#e6b34d;
--mid-bg:#3a3020;--accent:#8db8e3;--warn-bg:#3a3420}}
:root[data-theme="dark"]{--bg:#141517;--card:#1d1f22;--ink:#ececea;--muted:#a4a8ae;--line:#33363b;--ok:#7cc79a;
--ok-bg:#1f3327;--bad:#f08a83;--bad-bg:#3a1f1e;--mid:#e6b34d;--mid-bg:#3a3020;--accent:#8db8e3;--warn-bg:#3a3420}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1120px;margin:0 auto;padding:28px 16px 64px}h1{font-size:26px;margin:0 0 6px}
h2{font-size:19px;margin:36px 0 8px}h3{font-size:15px;margin:20px 0 6px}.sub{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0;
overflow-x:auto}.banner{background:var(--warn-bg);border:1px solid var(--line);border-radius:8px;padding:10px 14px;
font-weight:600}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}td.n{text-align:right}
.c{display:inline-block;min-width:34px;text-align:center;border-radius:6px;padding:1px 6px;font-size:12px;font-weight:600}
.ok{background:var(--ok-bg);color:var(--ok)}.bad{background:var(--bad-bg);color:var(--bad)}
.mid{background:var(--mid-bg);color:var(--mid)}.small{font-size:13px;color:var(--muted)}
footer{color:var(--muted);font-size:13px;margin-top:40px;border-top:1px solid var(--line);padding-top:12px}
"""

ROWS = [("Accuracy, all runs", "accuracy", "pct"), ("Questions right every run", "questions_right_every_run", ""),
        ("Consistency: all runs agree", "consistency_all_runs_agree", "pct"),
        ("Consistency: modal share", "consistency_modal_share", "pct"),
        ("Median numeric error", "median_numeric_error_pct", "pp"), ("Mean numeric error", "mean_numeric_error_pct", "pp"),
        ("Abstentions correct", "abstention_correct", ""), ("False abstentions", "false_abstentions", ""),
        ("Brief fields correct", "brief_fields_correct", ""), ("Brief unsupported $ figures",
                                                                "brief_unsupported_figures", ""),
        ("Validator send-backs", "validator_revisions", ""), ("Validator forced abstentions",
                                                             "validator_forced_abstentions", ""),
        ("Input tokens", "input_tokens", "int"), ("Output tokens", "output_tokens", "int"),
        ("Cost (USD)", "cost_usd", "usd"), ("Cost per question (USD)", "cost_per_question_usd", "usd4"),
        ("Mean turns", "mean_turns", ""), ("Median latency (s)", "median_latency_s", "")]


def fmt(v, k):
    if v is None:
        return "n/a"
    return {"pct": lambda: f"{v:.1%}", "pp": lambda: f"{v:.2f}%", "int": lambda: f"{v:,}",
            "usd": lambda: f"${v:,.2f}", "usd4": lambda: f"${v:,.4f}"}.get(k, lambda: str(v))()


def section(mode):
    d = RES / mode
    if not (d / "summary.json").exists():
        return ""
    s = json.loads((d / "summary.json").read_text())
    runs = [json.loads(l) for l in (d / "runs.jsonl").read_text().splitlines()]
    from evals.harness import BANNER
    V = list(s["variants"])
    out = [f"<h2>{html.escape(mode)} run</h2><div class=banner>{html.escape(BANNER[mode])}</div>",
           f"<p class=small>Model: {html.escape(s['model'])} · runs per question: {s['runs_per_question']} · "
           f"{'token counts estimated at ~4 characters per token' if s['tokens_are_estimates'] else 'tokens from the API'}"
           f" · cost priced as {html.escape(s.get('priced_as') or s['model'])} · generated {s['generated_at']}</p>",
           "<div class=card><table><tr><th>Metric</th>" + "".join(f"<th>{v}</th>" for v in V) + "</tr>"]
    for label, k, f in ROWS:
        out.append(f"<tr><td>{label}</td>" + "".join(f"<td class=n>{fmt(s['variants'][v][k], f)}</td>" for v in V)
                   + "</tr>")
    out.append("</table></div>")
    grid = defaultdict(lambda: defaultdict(list))
    for r in runs:
        grid[r["qid"]][r["variant"]].append(r)
    out.append("<h3>Question by question (runs right / runs)</h3><div class=card><table><tr><th>Q</th><th>Brand</th>"
               "<th>Question</th>" + "".join(f"<th>{v}</th>" for v in V) + "</tr>")
    for qid in sorted(grid, key=lambda q: (q == "B01", q)):
        cells = []
        for v in V:
            rs = grid[qid][v]
            k = sum(r["correct"] for r in rs)
            cls = "ok" if k == len(rs) else "bad" if k == 0 else "mid"
            fails = Counter(r["outcome"] for r in rs if not r["correct"])
            tip = ", ".join(f"{o} x{n}" for o, n in fails.items())
            cells.append(f"<td><span class='c {cls}' title='{html.escape(tip)}'>{k}/{len(rs)}</span>"
                         + (f"<div class=small>{html.escape(tip)}</div>" if tip else "") + "</td>")
        out.append(f"<tr><td>{qid}</td><td class=small>{html.escape(rs[0]['brand'])}</td>"
                   f"<td class=small>{html.escape(QTEXT[qid])}</td>{''.join(cells)}</tr>")
    out.append("</table></div><h3>Failure taxonomy by brand</h3><div class=card>")
    fb = s["failures_by_brand"]
    if not fb:
        out.append("<p>No failures.</p>")
    else:
        kinds = sorted({o for b in fb.values() for c in b.values() for o in c})
        out.append("<table><tr><th>Brand</th><th>Variant</th>" + "".join(f"<th>{k.replace('_', ' ')}</th>"
                                                                       for k in kinds) + "</tr>")
        for b in sorted(fb):
            for v in sorted(fb[b]):
                out.append(f"<tr><td>{html.escape(b)}</td><td>{v}</td>" + "".join(
                    f"<td class=n>{fb[b][v].get(k, '')}</td>" for k in kinds) + "</tr>")
        out.append("</table>")
    out.append("</div>")
    return "".join(out)


def scorer_section():
    p = RES / "scorer_validation.json"
    if not p.exists():
        return ""
    r = json.loads(p.read_text())
    rows = "".join(f"<tr><td>{html.escape(k.replace('_', ' '))}</td><td class=n>{v['reached_answer']}</td>"
                   f"<td class=n>{v['scored_wrong']}</td></tr>" for k, v in sorted(r["by_fault"].items()))
    c = r["clean"]
    return (f"<h2>Scorer check</h2><div class=card><p>The faulty mock injected known mistakes into "
            f"{r['runs']} runs. Every mistake that reached a final answer must be scored wrong, and every clean "
            f"answer scored right. Result: <b>{'pass' if r['all_faults_caught'] and r['no_false_flags'] else 'FAIL'}"
            f"</b>.</p><table><tr><th>Mistake type</th><th>Reached an answer</th><th>Scored wrong</th></tr>{rows}"
            f"<tr><td>clean answers</td><td class=n>{c['answers']}</td><td class=n>{c['answers'] - c['scored_correct']}"
            f"</td></tr></table><p class=small>The v3 validators sent back {r['v3_answers_sent_back']} answers and "
            f"forced {r['v3_forced_abstentions']} abstentions before scoring.</p></div>")


def build():
    live = section("live")
    body = (f"<h1>Workflow reliability lab</h1><p class=sub>The Fernwood Cash Brief workflow built three ways and "
            f"graded on 33 questions with exact answers, plus the brief itself.</p>"
            + ("" if live else "<div class=banner>No live run yet. Live scores exist only after a run with an API "
                               "key (make live). The sections below are offline mock runs.</div>")
            + live + section("mock") + scorer_section() + section("faulty"))
    OUT.write_text(f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport "
                   f"content='width=device-width,initial-scale=1'><title>Workflow Reliability</title>"
                   f"<style>{CSS}</style></head><body><main>{body}<footer>Built by Avinash Rayudu. All brands and "
                   f"numbers are synthetic.</footer></main></body></html>")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
