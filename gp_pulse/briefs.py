"""
Outreach brief generation — pluggable so the SAME calling code works
whether you're running offline (template mode, zero dependencies, zero
API cost) or wired up to a real LLM on hackathon day (one config flag:
GP_PULSE_BRIEF_MODE=llm).

The LLM path is implemented with urllib (standard library) against any
OpenAI-compatible chat-completions endpoint — OpenAI, Azure OpenAI,
GitHub Models, or a local Ollama/vLLM server all speak this same API
shape, so this works with whatever the hackathon actually hands you
without needing the `openai` pip package (which may not be installable
on a restricted network).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .config import BriefConfig
from .models import Brief, DriftResult

TALKING_POINTS = {
    "competitor_opened": [
        "Acknowledge convenience is likely the driver -- ask what would make Sonic the easier choice again.",
        "Offer on-site or more frequent collection at the practice to remove the travel-time gap.",
        "Highlight turnaround-time and result-quality differentiators versus the new competitor.",
    ],
    "staff_turnover": [
        "Check whether the new front-desk/practice-manager contact knows Sonic's booking process.",
        "Offer to re-run a quick refresher for reception staff on requisition/e-collect workflow.",
        "Confirm the GP's preferred contact hasn't changed along with the staff change.",
    ],
    "practice_acquired": [
        "Find out if the acquiring group has a preferred-lab agreement that's redirecting referrals.",
        "Position Sonic's network coverage/turnaround as compatible with the new group's requirements.",
        "Escalate to key-account team if this is part of a multi-practice group acquisition.",
    ],
    "unknown": [
        "Open with a genuine check-in call -- ask directly if anything has changed with their referral routing.",
        "Confirm there's no service issue (results delays, billing friction) driving the move.",
        "Use the visit to re-confirm current contact details and preferred collection times.",
    ],
}

CAUSE_LABELS = {
    "competitor_opened": "a competitor collection/imaging centre opening nearby",
    "staff_turnover": "recent staff turnover at the practice",
    "practice_acquired": "a practice acquisition/ownership change",
    "unknown": "no confirmed external cause",
}


class BriefGenerator(ABC):
    """Common interface both strategies implement."""

    @abstractmethod
    def generate(self, drift: DriftResult, context: dict | None) -> Brief:
        ...


class TemplateBriefGenerator(BriefGenerator):
    """Deterministic, offline, zero-cost. This is the safe fallback and
    the default — if the LLM path is unavailable or unconfigured on the
    day, briefs still come out looking like the real thing."""

    def generate(self, drift: DriftResult, context: dict | None) -> Brief:
        ctx = context or {}
        cause_code = ctx.get("cause_code", "unknown")
        cause_detail = ctx.get("cause_detail", "No related context events on record for this GP.")
        cause_label = CAUSE_LABELS.get(cause_code, CAUSE_LABELS["unknown"])
        talking_points = TALKING_POINTS.get(cause_code, TALKING_POINTS["unknown"])

        summary = (
            f"{drift.gp_name} ({drift.clinic}) has shown a sustained referral decline: "
            f"baseline average of {drift.baseline_avg}/month down to {drift.recent_avg}/month "
            f"over the last few months -- a {drift.drift_pct}% drop, flagged as {drift.severity} severity."
        )
        brief_text = (
            f"OUTREACH BRIEF -- {drift.gp_name}, {drift.clinic}\n"
            f"Severity: {drift.severity.upper()}\n\n"
            f"{summary}\n\n"
            f"Likely cause: {cause_label}. {cause_detail}\n\n"
            f"Suggested talking points:\n" + "\n".join(f"  - {p}" for p in talking_points)
        )
        return Brief(
            gp_id=drift.gp_id, gp_name=drift.gp_name, clinic=drift.clinic,
            severity=drift.severity, drift_pct=drift.drift_pct,
            cause_code=cause_code, cause_label=cause_label, cause_detail=cause_detail,
            talking_points=talking_points, summary=summary, brief_text=brief_text,
            generated_by="template",
        )


class LLMBriefGenerator(BriefGenerator):
    """Calls a real LLM to draft the brief. Falls back to the template
    generator automatically if the API call fails for any reason (no
    key configured, network blocked, rate limited, etc.) -- a live demo
    should never hard-fail because of a flaky network call."""

    def __init__(self, cfg: BriefConfig):
        self.cfg = cfg
        self._fallback = TemplateBriefGenerator()

    def _prompt(self, drift: DriftResult, context: dict) -> str:
        cause_code = context.get("cause_code", "unknown")
        cause_detail = context.get("cause_detail", "No related context events on record.")
        return (
            "You are drafting a short internal briefing for a pathology/radiology lab's "
            "relationship manager. A GP's referral volume has dropped versus their own "
            "historical baseline (never compare to other GPs). Write 3-4 factual, "
            "non-alarmist sentences: state the size of the drop, the likely cause, and "
            "2-3 concrete talking points for the RM's next call. Do not invent facts beyond "
            "what's given.\n\n"
            f"GP: {drift.gp_name}, {drift.clinic}, {drift.city}\n"
            f"Baseline referrals/month: {drift.baseline_avg}\n"
            f"Recent referrals/month: {drift.recent_avg}\n"
            f"Drift: {drift.drift_pct}% drop, severity {drift.severity}\n"
            f"Known context (may be 'unknown'): {cause_code} -- {cause_detail}\n"
        )

    def generate(self, drift: DriftResult, context: dict | None) -> Brief:
        ctx = context or {}
        if not self.cfg.api_key:
            return self._fallback.generate(drift, ctx)

        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": "You write concise, factual business-relationship briefs."},
                {"role": "user", "content": self._prompt(drift, ctx)},
            ],
            "temperature": 0.4,
        }
        req = urllib.request.Request(
            url=f"{self.cfg.api_base.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = body["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TimeoutError) as exc:
            fallback = self._fallback.generate(drift, ctx)
            fallback.brief_text += f"\n\n[LLM call failed, showing template brief instead: {exc}]"
            return fallback

        cause_code = ctx.get("cause_code", "unknown")
        cause_label = CAUSE_LABELS.get(cause_code, CAUSE_LABELS["unknown"])
        talking_points = TALKING_POINTS.get(cause_code, TALKING_POINTS["unknown"])
        return Brief(
            gp_id=drift.gp_id, gp_name=drift.gp_name, clinic=drift.clinic,
            severity=drift.severity, drift_pct=drift.drift_pct,
            cause_code=cause_code, cause_label=cause_label,
            cause_detail=ctx.get("cause_detail", ""),
            talking_points=talking_points, summary=text, brief_text=text,
            generated_by=f"llm:{self.cfg.model}",
        )


def get_generator(cfg: BriefConfig) -> BriefGenerator:
    """Factory — this is the one config flag (GP_PULSE_BRIEF_MODE) that
    switches the whole app from offline demo mode to live-LLM mode."""
    if cfg.mode == "llm":
        return LLMBriefGenerator(cfg)
    return TemplateBriefGenerator()
