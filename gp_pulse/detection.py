"""
Detection engine — the "Baseline Engine" from the pitch.

Compares each GP's recent referral volume to THEIR OWN historical
baseline (never an industry or peer benchmark), and flags only sustained,
meaningful drops — filtering out normal noise, seasonal dips, or GPs
already recovering.

Fully vectorized over pandas (no per-GP Python loop), so this scales from
the 16-GP hackathon demo to a full multi-thousand-GP referral panel with
the same code path — see tests/test_detection.py for a 2,000-GP timing
check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DetectionConfig
from .models import MONTHS, DriftResult


def _severity(drift_pct: float, cfg: DetectionConfig) -> str:
    if drift_pct >= cfg.high_severity_cutoff:
        return "high"
    if drift_pct >= cfg.medium_severity_cutoff:
        return "medium"
    return "low"


def run(df: pd.DataFrame, cfg: DetectionConfig) -> list[DriftResult]:
    """
    df must have columns: gp_id, gp_name, clinic, city, month, month_index,
    referral_count (the standardized ingestion schema).

    Returns one DriftResult per GP, sorted by drift_pct descending (worst
    first) — matches the "prioritised outreach list" from the pitch.
    """
    if df.empty:
        return []

    total_months = int(df["month_index"].max()) + 1
    baseline_cols = list(range(min(cfg.baseline_months, total_months)))
    recent_start = max(total_months - cfg.recent_window, 0)
    recent_cols = list(range(recent_start, total_months))

    # Wide matrix: one row per GP, one column per month_index.
    pivot = df.pivot_table(index="gp_id", columns="month_index", values="referral_count", aggfunc="first")
    pivot = pivot.reindex(columns=range(total_months))

    meta = df.drop_duplicates("gp_id").set_index("gp_id")[["gp_name", "clinic", "city"]]

    baseline_avg = pivot[baseline_cols].mean(axis=1)
    recent_avg = pivot[recent_cols].mean(axis=1)

    # Avoid divide-by-zero for a GP with a zero baseline (shouldn't happen
    # with real referral data, but don't blow up if it does).
    safe_baseline = baseline_avg.replace(0, np.nan)
    drift_pct = (baseline_avg - recent_avg) / safe_baseline
    drift_pct = drift_pct.fillna(0.0)

    # Each recent month individually must be meaningfully below baseline —
    # this is what stops a single bad month from tripping the flag.
    per_month_ok = pd.DataFrame(index=pivot.index)
    for c in recent_cols:
        per_month_ok[c] = (safe_baseline - pivot[c]) / safe_baseline >= cfg.per_month_min_below
    consistently_below = per_month_ok.fillna(False).all(axis=1)

    # Don't flag a GP that's already recovering — last recent month
    # shouldn't be meaningfully above the first recent month.
    non_recovering = pivot[recent_cols[-1]] <= pivot[recent_cols[0]] + 2

    flagged = (drift_pct >= cfg.drop_threshold) & consistently_below & non_recovering

    results: list[DriftResult] = []
    for gp_id in pivot.index:
        row = pivot.loc[gp_id]
        monthly_series = {MONTHS[i]: (int(row[i]) if not pd.isna(row[i]) else None) for i in range(total_months)}
        is_flagged = bool(flagged.loc[gp_id])
        dpct = round(float(drift_pct.loc[gp_id]) * 100, 1)
        results.append(DriftResult(
            gp_id=gp_id,
            gp_name=meta.loc[gp_id, "gp_name"],
            clinic=meta.loc[gp_id, "clinic"],
            city=meta.loc[gp_id, "city"],
            monthly_series=monthly_series,
            baseline_avg=round(float(baseline_avg.loc[gp_id]), 1),
            recent_avg=round(float(recent_avg.loc[gp_id]), 1),
            drift_pct=dpct,
            flagged=is_flagged,
            severity=_severity(dpct / 100, cfg) if is_flagged else None,
        ))

    results.sort(key=lambda r: r.drift_pct, reverse=True)
    return results
