"""GP Pulse — referral drift detection and outreach-brief engine.

A small, dependency-light service (standard library + pandas/numpy) that:
  1. ingests GP/clinic referral volume data (synthetic or real, same schema),
  2. detects sustained drift against each GP's OWN historical baseline,
  3. drafts an AI outreach brief for flagged GPs (template or real LLM call),
  4. serves it all over a plain-stdlib REST API for the dashboard to consume.

Designed to scale from the 16-GP hackathon demo dataset to a full Sonic
referral panel (tens of thousands of GPs) without changing the API shape —
the detection engine is vectorized over pandas, and storage is SQLite
(swap for Postgres by changing the connection string in storage.py when
this graduates beyond a hackathon prototype).
"""

__version__ = "0.2.0"
