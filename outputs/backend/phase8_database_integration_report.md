# PAIMANA AI — Phase 8 Database Integration Report

Scope: SQLite + SQLAlchemy persistence for the April 2026 snapshot, wired
into the existing FastAPI services. No retraining, no formula/threshold
changes, no frontend, no LLM/RAG, no deployment.

## 1. Database choice and location

- **SQLite** (stdlib `sqlite3` driver) + **SQLAlchemy ORM 2.0.36**, chosen
  because it needs no server, stores one portable file, and migrates to
  PostgreSQL later by changing only `PAIMANA_DATABASE_URL`.
- File: **`data/paimana.db`** (~3 MB, git-ignored via `.gitignore`; every
  environment builds its own with the documented commands).
- Sessions: per-request `get_db` dependency (commit/rollback/close); foreign
  keys enforced (`PRAGMA foreign_keys=ON`); startup performs no migration or
  import — only a reachability check and a warning with the exact commands.

## 2. Schema and relationships

| Table | Key columns |
|---|---|
| `projects` | `id` PK; `project_code` unique+indexed; name/agency/state (indexed); report month; 4 dates (NULLable); original/revised cost, expenditure, `physical_progress_pct` (NULLable). No sector column exists in the source — none was invented. |
| `risk_results` | `project_code` FK→projects + `report_month`, **composite unique**; cost/time/combined probabilities (`time_overrun_probability` NULLable — NULL, never 0); category/status/missing/formula-version; category indexed |
| `early_warnings` | same uniqueness; type/priority(+label)/message/indicators/action/explanation; project identity NOT duplicated (joined); priority indexed |
| `import_snapshots` | `snapshot_id` unique (`2026-04`); source files; reporting month; UTC timestamp; status; JSON summary |
| `schema_version` | applied migration versions (`0001_initial`) |

Relationships are FK-enforced (`projects.project_code` unique target);
future monthly snapshots slot into the same shape without touching old rows.

## 3. Files created or modified

Created: `backend/app/db/{__init__,base,session,models,migrations,init_db,import_snapshot,inspect_db}.py`,
`backend/tests/test_database.py`; root `.gitignore`.
Modified: `config.py` (+`PAIMANA_DATABASE_URL`), `services/project_service.py`
+ `services/risk_service.py` (DB-backed, same response contracts),
`api/{projects,risk,warnings,dashboard}.py` (DI sessions),
`tests/test_phase73_hardening.py` (unavailability tests now simulate DB
outage — same clean-500 assertions), `backend/requirements.txt` (+sqlalchemy),
`backend/README.md` (DB docs).
Unchanged: all of `ml/`, `models/`, `outputs/`, `main.py` routes/paths,
`schemas/`, prediction logic.

## 4-7. Import results (actual, verified)

- Source projects: **1981** — imported projects: **1981**
- Imported risk records: **1981** (NULL time probability: **354**)
- Imported warning records: **1981**
- Rerun import: `projects_new/risk_new/warnings_new = 0` — **idempotent**
- `risk_results.time_overrun_probability` NULL = 354; one project's risk row
  joins exactly to its own Phase-5 probabilities (e.g. 706724:
  cost 0.7251 / time 0.9894 / combined 0.8573).
- `risk/summary` from the DB: (1981, 765, 575, 641, 354, 380, 1239, 749) —
  exactly the Phase-5/6 artifact values; dashboard bins from the DB:
  90-100 = 589, 0-10 = 272 (incl. the 97 rows at exactly 100.0).
- Live prediction from saved models: cost 0.2218 / time 0.9995 — identical
  to the pre-database values.

## 8. Idempotency verification

- `python -m backend.app.db.import_snapshot` run **3 times** (twice during
  development, once for the final check): counts stayed at
  1981 / 1981 / 1981 every time, second+ runs reported `*_new = 0`.
- `apply_pending` twice on a scratch DB: second run applied `[]`.
- Tests assert counts are unchanged after a second import and that the
  `import_snapshots` row remains exactly one.

## 9. API integration results

- All existing routes unchanged except receiving a per-request session:
  `GET /`, `/health`, `/api/projects` (+search/pagination),
  `/api/projects/{code}`, `/api/projects/{code}/risk`,
  `/api/risk/summary`, `/api/early-warnings` (+filters/pagination),
  `/api/dashboard/progress-distribution` (+agency/state filters),
  `POST /api/predict`, `/docs`.
- 404/422/500/503 semantics preserved; invalid-pagination, invalid-filter,
  malformed-body and clean-error behaviours re-verified (suite + live).
- Dashboard progress endpoint now runs one SQL aggregate plus two
  single-row median queries per request (no full-dataset load).
- Startup loads the two models once; the database is only checked,
  never created or imported at startup.

## 10. Exact test results

`python -m unittest discover -s backend/tests -v` →
**Ran 77 tests — OK (exit 0), 0 failed**:
7 × 7.1 endpoints, 22 × 7.2 ML-API, 15 × 7.3 hardening,
16 × 7.4 dashboard graphs, 16 × **new 8.0 database tests**
(schema/migration, import counts, idempotent re-import, NULL time-prob,
rollback on mid-write failure, validation rejects mismatched sources,
FK integrity, API-on-temp-DB for projects/risk/warnings/dashboard/predict,
SQL bin edges 0/10/90/100 + NULL progress).
Baseline before Phase 8 was 61/61 — no baseline test was deleted or
weakened; two hardening tests were legitimately updated to simulate DB
outage instead of CSV absence (same clean-500 assertions).

## 11. Data-integrity/hash results

SHA-256 checked before Phase 8 and again after migration + full suite —
**all 7 tracked files UNCHANGED**: original, cleaned, feature CSVs
(`708A2FD9…`, `A7F330AC…`, `57819774…`); cost/time models
(`8769F00F…`, `450847CF…`); risk and warning CSVs (`2BC562BE…`,
`9C6AABF8…`). The live DB was re-imported after the suite with identical
counts; `data/paimana.db` itself is a generated (git-ignored) file.

## 12. Startup and migration commands (Windows PowerShell)

```powershell
pip install -r backend/requirements.txt
# $env:PAIMANA_DATABASE_URL = "sqlite:///C:/path/paimana.db"  # optional
python -m backend.app.db.init_db          # safe, never destructive
python -m backend.app.db.import_snapshot  # idempotent April-2026 import
python -m backend.app.db.inspect_db       # counts + provenance
uvicorn backend.app.main:app --reload --port 8000
python -m unittest discover -s backend/tests -v
```

## 13. Known limitations

- SQLite: single-writer semantics under heavy concurrency; tests use
  temporary files so the dev DB and CSVs are never at risk.
- Serves only the April 2026 snapshot associations (prototype scores, not
  verified forecasts); future snapshots import into new `report_month`
  rows — old rows are never deleted.
- No authentication/rate-limiting/deployment; no frontend.

## 14. Confirmation that the ML models were not retrained

- Model files byte-identical before/after (hashes above); prediction
  outputs identical to Phase 7 values (cost 0.2218 / time 0.9995 live);
  `predict_plan_only` and the `main.py` model lifecycle are untouched;
  feature schema, risk formulas, and 0.35/0.65 thresholds untouched
  (guarded by existing tests); source CSVs untouched.

