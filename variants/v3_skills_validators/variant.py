"""
Variant 3: skills, tools that do the arithmetic, and validators.

The model sees a short skill index and loads a skill's SKILL.md before using its
tools. Each tool computes a whole quantity from the definitions (a cash path, a
variance, a discount), so the model chooses rather than calculates.

Before an answer is accepted, two validators run:
  provenance    every number in the answer must appear in a tool result from this run
  coverage      if any tool said the data is missing, the answer must be an abstention
A failed check is sent back once for a revision. A second failure becomes an abstention.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from variants.common import DEFINITIONS, dollar_figures, numbers_in, parse_final, supported
from variants.v3_skills_validators import tools

NAME = "v3_skills_validators"
MAX_TURNS = 14
SKILLS = Path(__file__).resolve().parent.parent.parent / "skills"


def skill_index():
    out = []
    for p in sorted(SKILLS.glob("*/SKILL.md")):
        m = re.search(r"description:\s*(.+)", p.read_text())
        out.append(f"- {p.parent.name}: {m.group(1).strip() if m else ''}")
    return "\n".join(out)


def load_skill(name):
    p = SKILLS / name / "SKILL.md"
    return p.read_text() if p.exists() else json.dumps({"error": f"no skill {name!r}"})


def _flag(result: str) -> bool:
    try:
        r = json.loads(result)
    except json.JSONDecodeError:                 # skill text, not a tool result
        return False
    return isinstance(r, dict) and r.get("missing_data") is True


def validate(final_text: str, tool_results: list) -> str | None:
    """None if the answer passes; otherwise the message sent back to the model."""
    obj = parse_final(final_text)
    if obj is None:
        return "Your reply did not end with the required JSON object. Reply with only that JSON line."
    flagged = any(_flag(r) for r in tool_results)
    if obj.get("abstain") or ("narrative" in obj and flagged):
        return None
    if flagged:
        return ("A tool reported missing_data: true for this question. The data needed is missing, so you must "
                "abstain: answer null and abstain true.")
    seen = [n for r in tool_results if r.lstrip().startswith("{") for n in numbers_in(r)]
    if "narrative" in obj:                     # the brief: numeric fields plus every dollar figure in the text
        nums = [v for k, v in obj.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        nums += dollar_figures(obj.get("narrative"))
    else:
        ans = obj.get("answer")
        nums = numbers_in(ans) if not isinstance(ans, str) or re.fullmatch(r"-?[\d,.]+", ans or "") else []
    missing = [n for n in nums if not supported(n, seen)]
    if missing:
        return (f"These numbers in your answer do not appear in any tool result: {missing}. Use a tool that "
                f"computes the exact quantity and copy its value, or abstain.")
    return None


def build(question: str):
    system = (DEFINITIONS + "\n\n# Skills\nLoad the skill that fits before using its tools:\n" + skill_index() +
              "\n\nAnswer with numbers copied from tool results. Your answer is checked: any number not returned "
              "by a tool, or an answer given when a tool reported missing data, is sent back.")
    impl = {"load_skill": lambda a: load_skill(a["name"])}
    impl.update({t["name"]: (lambda n: (lambda a: tools.call(n, a)))(t["name"]) for t in tools.TOOLS
                 if t["name"] != "load_skill"})
    return dict(system=system, user=question, tools=tools.TOOLS, tool_impl=impl, validator=validate,
                max_turns=MAX_TURNS)
