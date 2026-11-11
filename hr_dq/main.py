"""Run the whole workflow: generate -> check -> autofix log -> AI proposals -> Excel report.

    python -m hr_dq.main --out output/hr_data_quality_report.xlsx
"""
import argparse
from pathlib import Path

import pandas as pd

from .agent import default_client, propose_fixes
from .checks import quality_score, run_checks, safe_autofix
from .excel_report import build_report
from .generate_data import generate


def monthly_trends(all_snaps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for snap, df in all_snaps.groupby("snapshot"):
        iss = run_checks(df)
        counts = iss["severity"].value_counts()
        rows.append({"month": snap, "high": int(counts.get("high", 0)), "medium": int(counts.get("medium", 0)),
                     "low": int(counts.get("low", 0)), "quality_score": quality_score(df, iss)})
    return pd.DataFrame(rows)


def run(out: str, n: int = 200, months: int = 6, seed: int = 42, client=None) -> dict:
    snaps = generate(n=n, months=months, seed=seed)
    latest_snap = snaps["snapshot"].max()
    latest = snaps[snaps["snapshot"] == latest_snap].reset_index(drop=True)
    issues = run_checks(latest)
    _, audit = safe_autofix(latest)
    proposals = propose_fixes(issues, latest, client=client)
    trends = monthly_trends(snaps)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    build_report(out, latest, issues, trends, proposals, audit, latest_snap)
    return {"snapshot": latest_snap, "employees": latest["employee_id"].nunique(), "issues": len(issues),
            "quality_score": quality_score(latest, issues), "proposals": len(proposals), "report": out}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/hr_data_quality_report.xlsx")
    ap.add_argument("--employees", type=int, default=200)
    a = ap.parse_args()
    print(run(a.out, n=a.employees, client=default_client()))
