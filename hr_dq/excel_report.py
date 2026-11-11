"""Build the Excel workbook HR colleagues actually open.

Sheets: Summary (live Excel formulas), Issues (Excel Table + filters + conditional
formatting), Trends (monthly error counts + native Excel line chart),
Employees (latest data, rows with issues highlighted), AI Suggestions, Audit Log.
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

RED, AMBER, GREY = PatternFill("solid", fgColor="F8CBAD"), PatternFill("solid", fgColor="FFE699"), \
    PatternFill("solid", fgColor="EDEDED")
BOLD = Font(bold=True)


def _write_df(ws, df: pd.DataFrame, table_name: str | None = None):
    ws.append(list(df.columns))
    for row in df.astype(object).where(df.notna(), None).itertuples(index=False):
        ws.append([str(v) if hasattr(v, "isoformat") else v for v in row])
    for c in ws[1]:
        c.font = BOLD
    for i, col in enumerate(df.columns, 1):
        width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(width, 45)
    ws.freeze_panes = "A2"
    if table_name and len(df):
        ref = f"A1:{get_column_letter(len(df.columns))}{len(df) + 1}"
        t = Table(displayName=table_name, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)


def build_report(path, latest: pd.DataFrame, issues: pd.DataFrame, trends: pd.DataFrame,
                 proposals: pd.DataFrame, audit: list[dict], snapshot: str) -> str:
    wb = Workbook()

    s = wb.active
    s.title = "Summary"
    s["A1"], s["A1"].font = f"Employee Data Quality Report - snapshot {snapshot}", Font(bold=True, size=14)
    affected = issues["employee_id"].nunique() if len(issues) else 0
    rows = [
        ("Employees", "=COUNTA(Employees!A:A)-1"),
        ("Total issues", "=COUNTA(Issues!A:A)-1"),
        ("High severity", '=COUNTIF(Issues!E:E,"high")'),
        ("Medium severity", '=COUNTIF(Issues!E:E,"medium")'),
        ("Low severity", '=COUNTIF(Issues!E:E,"low")'),
        ("Employees with issues", affected),
        ("Data quality score", "=1-B8/B3"),
        ("AI fix proposals awaiting approval", '=COUNTIF(\'AI Suggestions\'!H:H,"pending_human_approval")'),
    ]
    for i, (label, value) in enumerate(rows, start=3):
        s.cell(i, 1, label).font = BOLD
        s.cell(i, 2, value)
    s["B9"].number_format = "0.0%"
    s.conditional_formatting.add("B9", CellIsRule(operator="lessThan", formula=["0.95"], fill=RED))
    s.column_dimensions["A"].width = 36
    s.column_dimensions["B"].width = 14

    ws = wb.create_sheet("Issues")
    _write_df(ws, issues, "IssuesTable")
    n = len(issues) + 1
    ws.conditional_formatting.add(f"A2:F{n}", FormulaRule(formula=['$E2="high"'], fill=RED))
    ws.conditional_formatting.add(f"A2:F{n}", FormulaRule(formula=['$E2="medium"'], fill=AMBER))

    t = wb.create_sheet("Trends")
    _write_df(t, trends)
    chart = LineChart()
    chart.title, chart.y_axis.title, chart.x_axis.title = "Data issues per monthly snapshot", "Issues", "Month"
    data = Reference(t, min_col=2, max_col=4, min_row=1, max_row=len(trends) + 1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(Reference(t, min_col=1, min_row=2, max_row=len(trends) + 1))
    t.add_chart(chart, f"{get_column_letter(t.max_column + 2)}2")

    e = wb.create_sheet("Employees")
    _write_df(e, latest.drop(columns=["snapshot"]))
    bad = set(issues["employee_id"])
    for row in e.iter_rows(min_row=2):
        if row[0].value in bad:
            for c in row:
                c.fill = GREY

    _write_df(wb.create_sheet("AI Suggestions"), proposals, "Proposals")
    _write_df(wb.create_sheet("Audit Log"),
              pd.DataFrame(audit, columns=["employee_id", "field", "old", "new", "fixed_by"]))
    wb.save(path)
    return str(path)
