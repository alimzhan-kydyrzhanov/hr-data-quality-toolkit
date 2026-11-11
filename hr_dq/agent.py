"""Agentic AI step: an LLM agent that investigates each data issue with TOOLS
and proposes a fix. It never writes to the data: every proposal has
status 'pending_human_approval' (human-in-the-loop).

- With ANTHROPIC_API_KEY and the `anthropic` package: Claude runs a tool-use loop.
- Without them (or if the model answer is invalid): a rule-based fallback proposes the fix.
"""
import json
import os

import pandas as pd

from .generate_data import COST_CENTERS, COUNTRIES

ALLOWED_FIELDS = {"email", "termination_date", "hire_date", "manager_id", "cost_center",
                  "currency", "fte", "first_name", "last_name", "birth_date", "employee_id"}
MODEL = os.getenv("HR_DQ_MODEL", "claude-haiku-5-5")
MAX_STEPS = 5

TOOLS = [
    {"name": "get_employee", "description": "Return the full record of one employee by employee_id.",
     "input_schema": {"type": "object", "properties": {"employee_id": {"type": "string"}},
                      "required": ["employee_id"]}},
    {"name": "get_reference_data", "description": "Return valid cost centers and country->currency mapping.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "find_managers", "description": "Return employee_ids of Team Leads in a cost center.",
     "input_schema": {"type": "object", "properties": {"cost_center": {"type": "string"}},
                      "required": ["cost_center"]}},
]

SYSTEM = ("You are an HR data quality assistant. Investigate the issue with the tools, then answer ONLY with "
          'JSON: {"field": str, "proposed_value": str|null, "confidence": number 0-1, "reason": str}. '
          "If the correct value cannot be known from the data, set proposed_value to null and explain "
          "which person (employee, manager, HR) must confirm it.")


class Toolbox:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_employee(self, employee_id):
        rows = self.df[self.df["employee_id"] == employee_id]
        return rows.astype(str).to_dict("records")

    def get_reference_data(self):
        return {"cost_centers": COST_CENTERS, "currency_by_country": {c: v[1] for c, v in COUNTRIES.items()}}

    def find_managers(self, cost_center):
        m = (self.df["cost_center"] == cost_center) & (self.df["job_title"] == "Team Lead")
        return list(self.df.loc[m, "employee_id"])

    def call(self, name, args):
        return getattr(self, name)(**args)


def rule_based_proposal(issue: dict, tools: Toolbox) -> dict:
    rule, emp = issue["rule"], tools.get_employee(issue["employee_id"])
    rec = emp[0] if emp else {}
    p = {"field": issue["field"], "proposed_value": None, "confidence": 0.0, "reason": ""}
    if rule == "currency_country_mismatch":
        p.update(proposed_value=COUNTRIES[rec["country"]][1], confidence=0.95,
                 reason="Payroll currency follows the country of employment")
    elif rule == "name_formatting":
        p.update(proposed_value=issue["value"].strip().title(), confidence=0.9, reason="Trim and capitalize")
    elif rule == "manager_not_found":
        cands = tools.find_managers(rec.get("cost_center"))
        p.update(proposed_value=cands[0] if cands else None, confidence=0.4 if cands else 0.0,
                 reason="Team Lead in the same cost center - manager must confirm")
    else:
        p["reason"] = "Correct value is not in the data; confirm with the employee or HR business partner"
    return p


def validate(p) -> bool:
    return (isinstance(p, dict) and p.get("field") in ALLOWED_FIELDS
            and isinstance(p.get("confidence"), (int, float)) and 0 <= p["confidence"] <= 1
            and isinstance(p.get("reason"), str))


def llm_proposal(issue: dict, tools: Toolbox, client) -> dict | None:
    messages = [{"role": "user", "content": f"Data quality issue: {json.dumps(issue)}"}]
    for _ in range(MAX_STEPS):  # agent loop: think -> call tool -> observe -> repeat
        resp = client.messages.create(model=MODEL, max_tokens=500, system=SYSTEM, tools=TOOLS, messages=messages)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            try:
                p = json.loads(text[text.find("{"): text.rfind("}") + 1])
            except ValueError:
                return None
            return p if validate(p) else None
        messages.append({"role": "assistant", "content": resp.content})
        results = [{"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(tools.call(b.name, b.input))}
                   for b in resp.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})
    return None


def default_client():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except ImportError:
        return None


def propose_fixes(issues: pd.DataFrame, df: pd.DataFrame, client=None, limit: int = 30) -> pd.DataFrame:
    tools = Toolbox(df)
    out = []
    todo = issues[issues["severity"].isin(["high", "medium"])].head(limit)
    for issue in todo.to_dict("records"):
        p, source = None, "rule_based"
        if client is not None:
            try:
                p = llm_proposal(issue, tools, client)
                source = "llm_agent" if p else "rule_based (llm output invalid)"
            except Exception as e:  # network / API errors must not stop the report
                source = f"rule_based (llm error: {type(e).__name__})"
        if p is None:
            p = rule_based_proposal(issue, tools)
        out.append({"employee_id": issue["employee_id"], "rule": issue["rule"], **p,
                    "source": source, "status": "pending_human_approval"})
    return pd.DataFrame(out)
