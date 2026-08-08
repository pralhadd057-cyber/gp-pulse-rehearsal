"""
Data models for GP Pulse.

Plain dataclasses rather than pydantic — this keeps the whole service
runnable with zero pip installs beyond pandas/numpy (which are only used
for the vectorized detection math, not for data validation). Each model
carries a to_dict() for clean JSON serialization from the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class GPRecord:
    """Identity + metadata for a single GP/clinic being monitored."""

    gp_id: str
    gp_name: str
    clinic: str
    city: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DriftResult:
    """Output of the detection engine for a single GP."""

    gp_id: str
    gp_name: str
    clinic: str
    city: str
    monthly_series: dict  # {month_label: referral_count}
    baseline_avg: float
    recent_avg: float
    drift_pct: float
    flagged: bool
    severity: Optional[str]  # "high" | "medium" | "low" | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Brief:
    """AI-drafted (or template-drafted) outreach brief for a flagged GP."""

    gp_id: str
    gp_name: str
    clinic: str
    severity: str
    drift_pct: float
    cause_code: str
    cause_label: str
    cause_detail: str
    talking_points: list
    summary: str
    brief_text: str
    generated_by: str  # "template" | "llm:<model-name>"

    def to_dict(self) -> dict:
        return asdict(self)
