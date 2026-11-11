from types import SimpleNamespace as NS

import pandas as pd
from openpyxl import load_workbook

from hr_dq.agent import propose_fixes
from hr_dq.checks import run_checks
from hr_dq.generate_data import generate
from hr_dq.main import run


class FakeClient:
    """Imitates the Anthropic client: first asks for a tool, then answers with JSON."""

    def __init__(self, final_text):
        self.final_text, self.calls = final_text, 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        if self.calls % 2 == 1:
            block = NS(type="tool_use", id="t1", name="get_reference_data", input={})
            return NS(stop_reason="tool_use", content=[block])
        return NS(stop_reason="end_turn", content=[NS(type="text", text=self.final_text)])


def latest_with_issues():
    snaps = generate(n=150, months=2, seed=3)
    latest = snaps[snaps["snapshot"] == snaps["snapshot"].max()].reset_index(drop=True)
    return latest, run_checks(latest)


def test_rule_based_fallback_without_client():
    latest, issues = latest_with_issues()
    props = propose_fixes(issues, latest, client=None)
    assert len(props) > 0
    assert set(props["status"]) == {"pending_human_approval"}
    assert set(props["source"]) == {"rule_based"}


def test_llm_agent_uses_tools_and_valid_answer_is_accepted():
    latest, issues = latest_with_issues()
    client = FakeClient('{"field": "currency", "proposed_value": "CZK", "confidence": 0.9, "reason": "country"}')
    props = propose_fixes(issues.head(2), latest, client=client)
    assert set(props["source"]) == {"llm_agent"}
    assert client.calls == 4  # 2 issues x (tool call + final answer)


def test_invalid_llm_output_falls_back_to_rules():
    latest, issues = latest_with_issues()
    client = FakeClient('{"field": "salary", "proposed_value": "1", "confidence": 5, "reason": "?"}')
    props = propose_fixes(issues.head(1), latest, client=client)
    assert props.loc[0, "source"].startswith("rule_based")


def test_excel_report_structure(tmp_path):
    out = tmp_path / "report.xlsx"
    res = run(str(out), n=120, months=4, seed=7)
    wb = load_workbook(out)
    assert wb.sheetnames == ["Summary", "Issues", "Trends", "Employees", "AI Suggestions", "Audit Log"]
    assert wb["Summary"]["B9"].value == "=1-B8/B3"
    assert "IssuesTable" in wb["Issues"].tables
    assert len(wb["Trends"]._charts) == 1
    assert wb["Issues"].max_row == res["issues"] + 1
    trends = pd.read_excel(out, sheet_name="Trends")
    assert list(trends["month"]) == sorted(trends["month"])
