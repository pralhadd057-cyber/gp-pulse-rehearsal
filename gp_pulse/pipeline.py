"""
Pipeline orchestrator — wires ingestion -> storage -> detection -> briefs
into the one function the API (or a CLI, or a scheduled job) calls to
refresh everything.

Context events (the "why did this GP's referrals drop" signal that
briefs use) are pluggable too: pass your own dict of
{gp_id: {"cause_code": ..., "cause_detail": ...}} once you have a real
source (CRM notes, a BD spreadsheet, whatever), or leave it as None and
the pipeline assigns a plausible synthetic cause to each flagged GP,
deterministically by gp_id, so demo runs stay stable.
"""

from __future__ import annotations

import random

from . import briefs as briefs_mod
from . import detection, ingestion, storage
from .config import AppConfig

SYNTHETIC_CAUSES = [
    ("competitor_opened", "A competitor collection/imaging centre appears to have opened near this practice recently."),
    ("staff_turnover", "Practice records suggest recent staff turnover in the role that coordinates pathology bookings."),
    ("practice_acquired", "This practice appears to have changed ownership/group affiliation recently."),
    ("unknown", "No competitor openings or staffing changes detected in available records; cause not yet identified."),
]


def _synthetic_context(gp_ids: list[str]) -> dict:
    context = {}
    for gp_id in gp_ids:
        rng = random.Random(gp_id)  # deterministic per GP, independent of run order
        code, detail = rng.choice(SYNTHETIC_CAUSES)
        context[gp_id] = {"cause_code": code, "cause_detail": detail}
    return context


def run_pipeline(
    cfg: AppConfig,
    csv_path: str | None = None,
    n_gps: int = 16,
    context_events: dict | None = None,
) -> dict:
    """
    Runs the full pipeline once and persists results to SQLite.

    csv_path: if given, ingest real data from this path instead of
    generating synthetic data (this is the hackathon-day hook).
    Returns a small summary dict (counts), useful for API responses and
    logging.
    """
    if csv_path:
        df = ingestion.load_from_csv(csv_path)
    else:
        df = ingestion.generate_synthetic(n_gps=n_gps)

    with storage.connect(cfg.db_path) as conn:
        n_rows = storage.save_referrals(conn, df)

        results = detection.run(df, cfg.detection)
        storage.save_drift_results(conn, results)

        flagged = [r for r in results if r.flagged]
        ctx_events = context_events or _synthetic_context([r.gp_id for r in flagged])

        generator = briefs_mod.get_generator(cfg.brief)
        generated_briefs = [
            generator.generate(r, ctx_events.get(r.gp_id))
            for r in flagged
        ]
        storage.save_briefs(conn, generated_briefs)

    return {
        "referral_rows": n_rows,
        "gps_total": len({r.gp_id for r in results}),
        "gps_flagged": len(flagged),
        "briefs_generated": len(generated_briefs),
        "brief_mode": cfg.brief.mode,
    }
