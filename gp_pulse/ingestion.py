"""
Ingestion layer — the ONLY place that needs to change to point GP Pulse at
a real e-collect/LIS export instead of synthetic data.

Standardized output schema (a pandas DataFrame), used by every downstream
component:
    gp_id           stable identifier (str)
    gp_name         display name (str)
    clinic          clinic name (str)
    city            city (str)
    month           three-letter label, e.g. "Jan" (str)
    month_index     0-11, Jan=0 (int) — used for ordering
    referral_count  referrals that month (int)

Two entry points:
    generate_synthetic(n_gps=...)  — demo/test data, scales to any N.
    load_from_csv(path)            — real (or better-shaped) data, same
                                      schema; this is the hackathon-day
                                      hook if leadership provides a sample.
"""

from __future__ import annotations

import hashlib
import random

import pandas as pd

from .models import MONTHS

# Pattern library: each entry is a function of (baseline, month_index, rng)
# -> referral count for that month. Kept varied on purpose so a detector
# tuned only to catch real drift (not flag everything) has something to
# prove itself against.

PATTERNS = [
    "stable",
    "noisy_stable",
    "seasonal",
    "growth",
    "gradual_decline",
    "sharp_decline",
]

CITIES = ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Gold Coast", "Canberra", "Hobart", "Darwin", "Newcastle"]

FIRST_NAMES = [
    "Amanda", "Michael", "Sarah", "James", "Priya", "Robert", "Emily", "Andrew", "Lisa", "Tom",
    "Grace", "Daniel", "Rachel", "Kevin", "Olivia", "Chris", "Fatima", "Wei", "Noah", "Zara",
    "Liam", "Sophie", "Ethan", "Maria", "David", "Hannah", "Ben", "Chloe", "Ryan", "Ana",
]
LAST_NAMES = [
    "Chen", "Nguyen", "Thompson", "Wilson", "Sharma", "Lee", "Davis", "Kim", "Patel", "Anderson",
    "Liu", "Brown", "Green", "Zhang", "Martin", "Taylor", "Khan", "Wang", "Smith", "Ahmed",
    "Clark", "Walker", "Hall", "Young", "King", "Wright", "Lopez", "Hill", "Scott", "Adams",
]
CLINIC_WORDS_A = ["Riverside", "Parkview", "Coastal", "Uptown", "Greenfield", "Harbourside", "Northside",
                   "Sunset", "Meadowbrook", "Central", "Eastside", "Westfield", "Hillside", "Bayview",
                   "Fairview", "Riverbank", "Lakeside", "Southgate", "Willow", "Ashfield"]
CLINIC_WORDS_B = ["Family Medicine", "Medical Centre", "Health Clinic", "Family Practice", "Medical",
                   "Clinic", "GP Group", "Family Health", "Health Centre", "Group Practice"]


def _make_gp_id(gp_name: str, clinic: str) -> str:
    return hashlib.sha1(f"{gp_name}|{clinic}".encode()).hexdigest()[:10]


def _series_for_pattern(pattern: str, baseline: int, rng: random.Random) -> list[int]:
    series = []
    for i in range(12):
        if pattern == "stable":
            v = baseline + rng.randint(-4, 4)
        elif pattern == "noisy_stable":
            v = baseline + rng.randint(-7, 7)
        elif pattern == "seasonal":
            seasonal_adj = int(6 * (1 if i in (5, 6, 7) else -0.3))
            v = baseline + seasonal_adj + rng.randint(-3, 3)
        elif pattern == "growth":
            v = baseline + int(i * 1.4) + rng.randint(-3, 3)
        elif pattern == "gradual_decline":
            drop = max(0, (i - 4)) * rng.uniform(1.5, 2.5)
            v = baseline - int(drop) + rng.randint(-2, 2)
        elif pattern == "sharp_decline":
            v = (baseline + rng.randint(-3, 3)) if i < 7 else (int(baseline * 0.45) + rng.randint(-3, 3))
        else:
            v = baseline
        series.append(max(v, 1))
    return series


def generate_synthetic(n_gps: int = 16, seed: int = 42, decline_fraction: float = 0.35) -> pd.DataFrame:
    """
    Generate a synthetic referral panel of n_gps GPs across 12 months.

    decline_fraction controls roughly what share of GPs get a declining
    pattern (gradual or sharp) vs. stable/seasonal/growth — kept well
    under 1.0 so the detector has to actually discriminate, not just
    flag everyone. Deterministic for a given seed, so demo numbers don't
    shift between runs.
    """
    rng = random.Random(seed)
    rows = []

    for idx in range(n_gps):
        gp_name = f"Dr. {rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        clinic = f"{rng.choice(CLINIC_WORDS_A)} {rng.choice(CLINIC_WORDS_B)}"
        city = rng.choice(CITIES)
        gp_id = _make_gp_id(f"{gp_name}#{idx}", clinic)  # index keeps ids unique even with name collisions
        baseline = rng.randint(20, 70)

        if rng.random() < decline_fraction:
            pattern = rng.choice(["gradual_decline", "sharp_decline"])
        else:
            pattern = rng.choice(["stable", "noisy_stable", "seasonal", "growth"])

        series = _series_for_pattern(pattern, baseline, rng)
        for month_index, count in enumerate(series):
            rows.append({
                "gp_id": gp_id,
                "gp_name": gp_name,
                "clinic": clinic,
                "city": city,
                "month": MONTHS[month_index],
                "month_index": month_index,
                "referral_count": count,
            })

    return pd.DataFrame(rows)


REQUIRED_COLUMNS = {"gp_name", "clinic", "city", "month", "referral_count"}


def load_from_csv(path: str) -> pd.DataFrame:
    """
    Load real (or better-shaped) referral data. Expects at minimum:
    gp_name, clinic, city, month, referral_count. month can be a
    three-letter label ("Jan") or 1-12 / 0-11 int — normalized here.
    gp_id is derived if not present, so this works directly against an
    export that doesn't already have a stable GP identifier.
    """
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    if "gp_id" not in df.columns:
        df["gp_id"] = df.apply(lambda r: _make_gp_id(str(r["gp_name"]), str(r["clinic"])), axis=1)

    if "month_index" not in df.columns:
        if pd.api.types.is_numeric_dtype(df["month"]):
            # Accept either 1-12 or 0-11 numeric months.
            df["month_index"] = df["month"].astype(int).apply(lambda m: m - 1 if m >= 1 and m <= 12 and m != 0 else m)
        else:
            month_map = {m: i for i, m in enumerate(MONTHS)}
            df["month_index"] = df["month"].map(month_map)
            if df["month_index"].isna().any():
                bad = df.loc[df["month_index"].isna(), "month"].unique()
                raise ValueError(f"Unrecognized month labels: {list(bad)}. Expected {MONTHS}.")
            df["month_index"] = df["month_index"].astype(int)

    df["referral_count"] = df["referral_count"].astype(int)
    return df.sort_values(["gp_id", "month_index"]).reset_index(drop=True)
