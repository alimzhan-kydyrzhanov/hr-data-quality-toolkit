"""Data quality rules for employee master data.

Each check takes the DataFrame of ONE snapshot and returns a list of issue dicts.
Nothing is deleted or changed here: checks only REPORT (like a validation report
in an HR system). Safe, reversible fixes live in `safe_autofix`.
"""
import re
from datetime import date

import pandas as pd

from .generate_data import COST_CENTERS, COUNTRIES

MANDATORY = ["employee_id", "first_name", "last_name", "email", "hire_date", "country", "cost_center"]
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
ISSUE_COLUMNS = ["employee_id", "field", "value", "rule", "severity", "message"]


def _issue(row, field, rule, severity, message):
    return {"employee_id": row.get("employee_id"), "field": field, "value": str(row.get(field)),
            "rule": rule, "severity": severity, "message": message}


def check_mandatory(df, ref):
    out = []
    for _, r in df.iterrows():
        for f in MANDATORY:
            if pd.isna(r[f]) or str(r[f]).strip() == "":
                out.append(_issue(r, f, "missing_mandatory", "high", f"Mandatory field '{f}' is empty"))
    return out


def check_duplicate_ids(df, ref):
    dups = df[df.duplicated("employee_id", keep="first")]
    return [_issue(r, "employee_id", "duplicate_id", "high", "Employee ID appears more than once")
            for _, r in dups.iterrows()]


def check_email_format(df, ref):
    bad = df[df["email"].notna() & ~df["email"].astype(str).str.match(EMAIL_RE)]
    return [_issue(r, "email", "invalid_email", "medium", "Email address has an invalid format")
            for _, r in bad.iterrows()]


def check_termination_before_hire(df, ref):
    m = df["termination_date"].notna() & (pd.to_datetime(df["termination_date"]) < pd.to_datetime(df["hire_date"]))
    return [_issue(r, "termination_date", "termination_before_hire", "high", "Termination date is before hire date")
            for _, r in df[m].iterrows()]


def check_future_hire(df, ref):
    m = pd.to_datetime(df["hire_date"]) > pd.Timestamp(ref) + pd.Timedelta(days=180)
    return [_issue(r, "hire_date", "future_hire_date", "medium", "Hire date is more than 6 months in the future")
            for _, r in df[m].iterrows()]


def check_manager_exists(df, ref):
    ids = set(df["employee_id"])
    m = df["manager_id"].notna() & ~df["manager_id"].isin(ids)
    return [_issue(r, "manager_id", "manager_not_found", "medium", "Manager ID does not exist in employee data")
            for _, r in df[m].iterrows()]


def check_cost_center(df, ref):
    m = df["cost_center"].notna() & ~df["cost_center"].isin(COST_CENTERS)
    return [_issue(r, "cost_center", "invalid_cost_center", "medium", "Cost center is not in the master list")
            for _, r in df[m].iterrows()]


def check_currency(df, ref):
    expected = df["country"].map(lambda c: COUNTRIES.get(c, (None, None))[1])
    m = df["currency"] != expected
    return [_issue(r, "currency", "currency_country_mismatch", "medium",
                   f"Currency {r['currency']} does not match country {r['country']}")
            for _, r in df[m].iterrows()]


def check_fte(df, ref):
    m = (df["fte"] <= 0) | (df["fte"] > 1)
    return [_issue(r, "fte", "fte_out_of_range", "medium", "FTE must be > 0 and <= 1")
            for _, r in df[m].iterrows()]


def check_name_format(df, ref):
    out = []
    for _, r in df.iterrows():
        for f in ("first_name", "last_name"):
            v = r[f]
            if isinstance(v, str) and (v != v.strip() or v.strip() != v.strip().title()):
                out.append(_issue(r, f, "name_formatting", "low", "Name has extra spaces or wrong capitalization"))
    return out


def check_age_at_hire(df, ref):
    age = (pd.to_datetime(df["hire_date"]) - pd.to_datetime(df["birth_date"])).dt.days / 365.25
    return [_issue(r, "birth_date", "underage_at_hire", "high", "Employee was younger than 16 at hire")
            for _, r in df[age < 16].iterrows()]


CHECKS = [check_mandatory, check_duplicate_ids, check_email_format, check_termination_before_hire,
          check_future_hire, check_manager_exists, check_cost_center, check_currency, check_fte,
          check_name_format, check_age_at_hire]


def run_checks(df: pd.DataFrame, ref: date = date(2026, 10, 31)) -> pd.DataFrame:
    issues = [i for check in CHECKS for i in check(df, ref)]
    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def safe_autofix(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Apply only fixes that cannot change meaning (whitespace, capitalization, email case).
    Every change is written to an audit log: who/what/old/new, so it can be reviewed."""
    fixed = df.copy()
    audit = []
    for idx, r in fixed.iterrows():
        for f in ("first_name", "last_name"):
            v = r[f]
            if isinstance(v, str) and v.strip().title() != v:
                fixed.at[idx, f] = v.strip().title()
                audit.append({"employee_id": r["employee_id"], "field": f, "old": v, "new": v.strip().title(),
                              "fixed_by": "safe_autofix"})
        e = r["email"]
        if isinstance(e, str) and e.strip().lower() != e:
            fixed.at[idx, "email"] = e.strip().lower()
            audit.append({"employee_id": r["employee_id"], "field": "email", "old": e, "new": e.strip().lower(),
                          "fixed_by": "safe_autofix"})
    return fixed, audit


def quality_score(df: pd.DataFrame, issues: pd.DataFrame) -> float:
    """Share of employees with zero issues (0..1)."""
    total = df["employee_id"].nunique()
    affected = issues["employee_id"].nunique() if len(issues) else 0
    return round(1 - affected / total, 4) if total else 1.0
