from datetime import date

import pandas as pd

from hr_dq.checks import quality_score, run_checks, safe_autofix
from hr_dq.generate_data import generate


def good_row(**over):
    row = {"snapshot": "2026-10", "employee_id": "E1", "first_name": "Anna", "last_name": "Novak",
           "email": "anna.novak@example.com", "birth_date": date(1995, 1, 1), "hire_date": date(2020, 1, 1),
           "termination_date": None, "country": "CZ", "office": "Prague", "currency": "CZK",
           "cost_center": "CC100", "job_title": "HR Specialist", "fte": 1.0, "manager_id": None}
    row.update(over)
    return row


def rules(rows):
    return set(run_checks(pd.DataFrame(rows))["rule"])


def test_clean_record_has_no_issues():
    assert rules([good_row()]) == set()


def test_each_rule_detects_its_error():
    cases = {
        "missing_mandatory": good_row(email=None),
        "invalid_email": good_row(email="anna at example.com"),
        "termination_before_hire": good_row(termination_date=date(2019, 1, 1)),
        "future_hire_date": good_row(hire_date=date(2028, 1, 1)),
        "manager_not_found": good_row(manager_id="E404"),
        "invalid_cost_center": good_row(cost_center="CC999"),
        "currency_country_mismatch": good_row(currency="EUR"),
        "fte_out_of_range": good_row(fte=1.5),
        "name_formatting": good_row(first_name="  ANNA "),
        "underage_at_hire": good_row(birth_date=date(2010, 1, 1)),
    }
    for rule, row in cases.items():
        assert rule in rules([row]), rule


def test_duplicate_id_flagged_once():
    iss = run_checks(pd.DataFrame([good_row(), good_row(email="x@example.com")]))
    assert (iss["rule"] == "duplicate_id").sum() == 1


def test_autofix_only_safe_fields_and_logs_changes():
    df = pd.DataFrame([good_row(first_name="  ANNA ", email="Anna.Novak@Example.com", currency="EUR")])
    fixed, audit = safe_autofix(df)
    assert fixed.loc[0, "first_name"] == "Anna"
    assert fixed.loc[0, "email"] == "anna.novak@example.com"
    assert fixed.loc[0, "currency"] == "EUR"  # meaning-changing fields are never auto-fixed
    assert {a["field"] for a in audit} == {"first_name", "email"}


def test_generated_data_gets_cleaner_over_time():
    snaps = generate(n=300, months=6, seed=1)
    scores = [quality_score(d, run_checks(d)) for _, d in snaps.groupby("snapshot")]
    assert scores[-1] > scores[0]
