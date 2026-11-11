# HR Employee Data Quality Toolkit

Checks employee master data (HR records) for errors and inconsistencies, produces an
**Excel report** for HR colleagues, and uses an **AI agent** to propose fixes that a
human approves. All data is **synthetic** (no real people).

## What it does
1. **Generates** 6 monthly snapshots of synthetic employee data (5 countries incl. CZ/Prague, JP, IN) with injected errors.
2. **Runs 11 data quality checks**: missing mandatory fields, duplicate employee IDs, invalid email,
   termination before hire, future hire date, manager not found, invalid cost center,
   currency/country mismatch, FTE out of range, name formatting, age at hire < 16.
3. **Safe auto-fix** of meaning-neutral problems (spaces, capitalization) with an **audit log**.
4. **AI agent** (Claude, tool use) investigates each high/medium issue with tools
   (`get_employee`, `get_reference_data`, `find_managers`) and proposes a fix with confidence
   and reason. Output is validated; on invalid output or no API key a rule-based fallback is used.
   Every proposal is `pending_human_approval` — the agent never edits data.
5. **Excel report** (`openpyxl`): Summary with live formulas (`COUNTIF`, quality score),
   Issues as an Excel Table with filters and conditional formatting, Trends with a line chart,
   Employees with problem rows highlighted, AI Suggestions, Audit Log.

## Run
```bash
pip install -r requirements.txt
python -m pytest -q
python -m hr_dq.main --out output/hr_data_quality_report.xlsx
# optional LLM agent:
pip install anthropic && export ANTHROPIC_API_KEY=...   # model: HR_DQ_MODEL env var
```
Docker: `docker build -t hr-dq . && docker run --rm -v $PWD/output:/app/output hr-dq`

## Structure
```
hr_dq/generate_data.py   synthetic employee snapshots + injected errors
hr_dq/checks.py          11 data quality rules, safe autofix + audit log, quality score
hr_dq/agent.py           AI agent (tool-use loop), validation, rule-based fallback
hr_dq/excel_report.py    Excel workbook: formulas, table, conditional formatting, chart
hr_dq/main.py            end-to-end workflow + monthly trends
tests/                   pytest (rules, autofix, agent with fake client, Excel structure)
```
