"""
Central configuration for GP Pulse.

Everything tunable lives here (or is overridable via environment variables)
so the detection thresholds and brief-generation mode can be changed
without touching logic code — important on hackathon day when you'll want
to retune against whatever real-shaped data you get, live, without
hunting through multiple files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val is not None else default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val is not None else default


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class DetectionConfig:
    """Tunable parameters for the baseline drift engine."""

    # How many of the earliest months in a GP's series establish "normal".
    baseline_months: int = field(default_factory=lambda: _env_int("GP_PULSE_BASELINE_MONTHS", 6))
    # Trailing window checked for a sustained (not one-off) drop.
    recent_window: int = field(default_factory=lambda: _env_int("GP_PULSE_RECENT_WINDOW", 3))
    # Overall drop (baseline avg -> recent avg) required to flag at all.
    drop_threshold: float = field(default_factory=lambda: _env_float("GP_PULSE_DROP_THRESHOLD", 0.20))
    # Each month in the recent window must individually be at least this
    # far below baseline, so one bad month can't drag the average down
    # and trigger a false flag.
    per_month_min_below: float = field(default_factory=lambda: _env_float("GP_PULSE_PER_MONTH_MIN_BELOW", 0.10))
    # Severity tier cutoffs (drift %).
    high_severity_cutoff: float = field(default_factory=lambda: _env_float("GP_PULSE_HIGH_CUTOFF", 0.40))
    medium_severity_cutoff: float = field(default_factory=lambda: _env_float("GP_PULSE_MEDIUM_CUTOFF", 0.25))


@dataclass
class BriefConfig:
    """Which brief generation strategy to use, and how to reach an LLM if so."""

    # "template" (offline, deterministic, zero dependencies) or "llm"
    # (calls an OpenAI-compatible chat completions endpoint).
    mode: str = field(default_factory=lambda: _env_str("GP_PULSE_BRIEF_MODE", "template"))
    # Any OpenAI-compatible endpoint: OpenAI, Azure OpenAI, GitHub Models,
    # a local vLLM/Ollama server, etc. Only used when mode == "llm".
    api_base: str = field(default_factory=lambda: _env_str("GP_PULSE_LLM_API_BASE", "https://api.openai.com/v1"))
    api_key: str = field(default_factory=lambda: _env_str("GP_PULSE_LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "")))
    model: str = field(default_factory=lambda: _env_str("GP_PULSE_LLM_MODEL", "gpt-4o-mini"))
    timeout_seconds: int = field(default_factory=lambda: _env_int("GP_PULSE_LLM_TIMEOUT", 20))


@dataclass
class AppConfig:
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    brief: BriefConfig = field(default_factory=BriefConfig)
    db_path: str = field(default_factory=lambda: _env_str("GP_PULSE_DB_PATH", "gp_pulse.sqlite3"))
    api_host: str = field(default_factory=lambda: _env_str("GP_PULSE_API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _env_int("GP_PULSE_API_PORT", 8000))


def load_config() -> AppConfig:
    """Single entry point the rest of the app uses to get configuration."""
    return AppConfig()
