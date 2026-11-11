"""Generate SYNTHETIC employee master data with injected data quality errors.

No real people: names are random combinations, IDs are fake.
Produces several monthly snapshots so the Excel report can show trends
(the error rate goes down month by month, as if the team were fixing data).
"""
import random
from datetime import date, timedelta

import pandas as pd

COUNTRIES = {  # country -> (office city, payroll currency)
    "CZ": ("Prague", "CZK"),
    "DE": ("Walldorf", "EUR"),
    "IN": ("Bangalore", "INR"),
    "JP": ("Tokyo", "JPY"),
    "US": ("Newtown Square", "USD"),
}
COST_CENTERS = ["CC100", "CC200", "CC300", "CC400"]
TITLES = ["HR Specialist", "Data Analyst", "Software Engineer", "Payroll Specialist", "Team Lead"]
FIRST = ["Anna", "Jan", "Petra", "Lukas", "Mei", "Ravi", "Yuki", "Sara", "Tomas", "Kenji", "Lena", "Arjun"]
LAST = ["Novak", "Svoboda", "Muller", "Schmidt", "Tanaka", "Sato", "Sharma", "Patel", "Smith", "Brown"]

ERROR_TYPES = [
    "missing_email", "bad_email", "duplicate_id", "termination_before_hire",
    "future_hire", "unknown_manager", "bad_cost_center", "wrong_currency",
    "bad_fte", "messy_name", "underage",
]


def _base_employees(n: int, rng: random.Random) -> list[dict]:
    rows = []
    for i in range(n):
        country = rng.choice(list(COUNTRIES))
        first, last = rng.choice(FIRST), rng.choice(LAST)
        hire = date(2015, 1, 1) + timedelta(days=rng.randint(0, 3500))
        birth = hire - timedelta(days=rng.randint(22 * 365, 50 * 365))
        rows.append({
            "employee_id": f"E{10000 + i}",
            "first_name": first,
            "last_name": last,
            "email": f"{first}.{last}{i}@example.com".lower(),
            "birth_date": birth,
            "hire_date": hire,
            "termination_date": None,
            "country": country,
            "office": COUNTRIES[country][0],
            "currency": COUNTRIES[country][1],
            "cost_center": rng.choice(COST_CENTERS),
            "job_title": rng.choice(TITLES),
            "fte": rng.choice([1.0, 1.0, 1.0, 0.8, 0.5]),
            "manager_id": None if i < 5 else f"E{10000 + rng.randint(0, 4)}",
        })
    return rows


def _inject(row: dict, kind: str, rng: random.Random, ref: date) -> dict:
    r = dict(row)
    if kind == "missing_email":
        r["email"] = None
    elif kind == "bad_email":
        r["email"] = r["email"].replace("@", " at ") if r["email"] else "no-email"
    elif kind == "termination_before_hire":
        r["termination_date"] = r["hire_date"] - timedelta(days=30)
    elif kind == "future_hire":
        r["hire_date"] = ref + timedelta(days=400)
    elif kind == "unknown_manager":
        r["manager_id"] = "E99999"
    elif kind == "bad_cost_center":
        r["cost_center"] = "CC999"
    elif kind == "wrong_currency":
        r["currency"] = "EUR" if r["currency"] != "EUR" else "USD"
    elif kind == "bad_fte":
        r["fte"] = rng.choice([0.0, 1.5, 10.0])
    elif kind == "messy_name":
        r["first_name"] = f"  {r['first_name'].upper()} "
    elif kind == "underage":
        r["birth_date"] = r["hire_date"] - timedelta(days=14 * 365)
    return r


def generate(n: int = 200, months: int = 6, seed: int = 42,
             start_error_rate: float = 0.12, ref: date = date(2026, 10, 31)) -> pd.DataFrame:
    """Return all monthly snapshots in one DataFrame with a `snapshot` column (YYYY-MM)."""
    rng = random.Random(seed)
    base = _base_employees(n, rng)
    frames = []
    for m in range(months):
        snap = (pd.Timestamp(ref) - pd.DateOffset(months=months - 1 - m)).strftime("%Y-%m")
        rate = start_error_rate * (1 - m / (months + 1))  # data gets cleaner over time
        rows = []
        for row in base:
            if rng.random() < rate:
                kind = rng.choice(ERROR_TYPES)
                if kind == "duplicate_id":
                    rows.append(row)
                    dup = dict(row)
                    dup["email"] = f"dup.{row['email']}"
                    rows.append(dup)
                    continue
                row = _inject(row, kind, rng, ref)
            rows.append(row)
        df = pd.DataFrame(rows)
        df.insert(0, "snapshot", snap)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    print(generate().groupby("snapshot").size())
