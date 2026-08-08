# GP Pulse

Referral-drift detection and AI outreach briefs for pathology/radiology relationship management. Flags GPs whose referral volume has dropped against **their own** historical baseline (never an industry benchmark), and drafts a relationship-manager brief explaining the likely cause and suggested talking points.

Built for the Sonic Healthcare hackathon. All data shipped in this repo is **synthetic** — no real patient or referral data.

## Architecture

```
gp_pulse/
  ingestion.py    -- loads referral data: synthetic generator (any N GPs) or real CSV import
  detection.py    -- vectorized (pandas) baseline drift engine; scales to thousands of GPs
  briefs.py        -- pluggable brief generator: template (offline) or real LLM call
  storage.py        -- SQLite persistence
  pipeline.py        -- orchestrates ingestion -> detection -> briefs -> storage
  api.py               -- REST API + dashboard server, standard library only
frontend/
  dashboard.html        -- single-page dashboard, fetches live from the API
tests/                    -- unittest suite (31 tests): correctness, edge cases, scale, API
```

**Deliberately dependency-light.** The API server, storage, and template brief generation use only the Python standard library (`http.server`, `sqlite3`, `urllib`). Only the detection engine needs pandas/numpy. This means the whole thing runs with one `pip install -r requirements.txt` and nothing else — no FastAPI, no ORM, no `openai` SDK — which matters if you're on a hackathon network where pip installs might be slow or partially blocked.

## Quickstart

```bash
pip install -r requirements.txt
python3 -m gp_pulse seed --n-gps 16     # generate synthetic data, run detection + briefs
python3 -m gp_pulse serve                # start API + dashboard at http://127.0.0.1:8000
```

Or just run `./run.sh` (or `./run.sh 500` to seed 500 GPs instead of the default 16).

Open `http://127.0.0.1:8000/` — that's the dashboard, served by the same process, fetching live from the API. Type a number into the "Regenerate + recompute" box and click it to watch the whole pipeline re-run in the browser (this is a good live-demo move: show it working at 16 GPs, then again at 2,000, without touching the terminal).

## Using real data instead of synthetic

```bash
python3 -m gp_pulse seed --csv path/to/export.csv
```

The CSV needs at minimum: `gp_name, clinic, city, month, referral_count`. `month` can be `Jan`-`Dec` or a 1-12 number. Everything else (a stable `gp_id`, month ordering) is derived automatically. See `gp_pulse/ingestion.py::load_from_csv`.

## Switching from template briefs to a real LLM

One environment variable:

```bash
export GP_PULSE_BRIEF_MODE=llm
export GP_PULSE_LLM_API_KEY=sk-...
export GP_PULSE_LLM_API_BASE=https://api.openai.com/v1   # or Azure OpenAI / GitHub Models / a local Ollama server
export GP_PULSE_LLM_MODEL=gpt-4o-mini
python3 -m gp_pulse seed --n-gps 16
```

If the API call fails for any reason (no key, network blocked, rate limited), `LLMBriefGenerator` automatically falls back to the template generator rather than crashing the pipeline — a live demo should never hard-fail on a flaky network call. Check `generated_by` on any brief (`"template"` vs `"llm:<model>"`) to see which path actually ran.

## Tuning detection thresholds

Also environment variables (see `gp_pulse/config.py` for the full list and defaults):

| Variable | Default | Meaning |
|---|---|---|
| `GP_PULSE_BASELINE_MONTHS` | 6 | Months used to establish "normal" for a GP |
| `GP_PULSE_RECENT_WINDOW` | 3 | Trailing months checked for a sustained drop |
| `GP_PULSE_DROP_THRESHOLD` | 0.20 | Overall drop required to flag at all |
| `GP_PULSE_PER_MONTH_MIN_BELOW` | 0.10 | Each recent month must individually be this far below baseline |
| `GP_PULSE_HIGH_CUTOFF` / `GP_PULSE_MEDIUM_CUTOFF` | 0.40 / 0.25 | Severity tier cutoffs |

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

31 tests covering: detection correctness (the worked example, stable GPs not flagged, seasonal dips not flagged, single bad months not flagged, sustained declines flagged), a performance check (2,000 GPs detected in well under 5 seconds), brief generation (template output, graceful LLM fallback), ingestion (schema validation, CSV error handling), the full pipeline end-to-end, and every API endpoint against a live server instance.

## Docker

```bash
docker build -t gp-pulse .
docker run -p 8000:8000 -e GP_PULSE_SEED_N_GPS=200 gp-pulse
```

## REST API reference

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness + current brief mode |
| GET | `/api/gps` | All monitored GPs, worst drift first |
| GET | `/api/gps/flagged` | Only flagged GPs |
| GET | `/api/gps/<gp_id>` | Single GP detail |
| GET | `/api/briefs` | All generated briefs |
| GET | `/api/briefs/<gp_id>` | Single brief |
| POST | `/api/recompute` | Re-run the pipeline. Body: `{"n_gps": 200}` or `{"csv_path": "..."}` |
| GET | `/` | Dashboard (serves `frontend/dashboard.html`) |

## Why this design, for judges asking about feasibility

- **Ingestion is a single swap point.** `load_from_csv` already expects a plain, realistic schema — pointing this at a real e-collect/LIS export is a data-mapping exercise, not a rewrite.
- **Detection is vectorized, not a per-GP loop.** Verified to process 2,000 GPs (24,000 referral-months) in about 1 second — this scales to Sonic's actual referral panel without an architecture change.
- **The brief generator is a strategy pattern.** Ships in offline/template mode so the demo never depends on network access or an API key being available at the right moment, but is one environment variable away from a real LLM call — no code changes needed to go from hackathon demo to pilot.
- **Storage is SQLite now, Postgres-ready later.** Plain SQL, no ORM lock-in; moving to a shared database when this leaves "prototype" is a connection-string change, not a rewrite.
- **Zero required external services.** No message queue, no managed API dependency beyond the optional LLM call. Deliverable by an existing squad inside a normal sprint, which is exactly the "speed to value" the judging criteria ask about.
