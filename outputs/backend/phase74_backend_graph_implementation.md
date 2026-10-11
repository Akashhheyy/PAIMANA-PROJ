# PAIMANA AI — Phase 7.4 Prompt 2: Backend Graph-Data Implementation

Backend only. No frontend, no model retraining, no formula/threshold
changes, no database.

## 1. Endpoint contract (new)

```
GET /api/dashboard/progress-distribution?agency=<optional>&state=<optional>
```

| Aspect | Contract |
|---|---|
| Purpose | Physical-progress distribution for the general dashboard (Graph 1) |
| Data source | Cached `projects_frame()` (`paimana_features.csv`) — **CSV read once, not per request** |
| Filters | `agency`, `state` — optional, exact match, `1..200` chars (empty/overlong → 422) |
| Bins | 10 bins `[0,10], (10,20], …, (90,100]` — **last bin includes exactly 100%** |
| Guarantees | `sum(bins.count) == projects_included` (runtime assertion); every eligible project in exactly one bin; missing progress excluded from bins and counted in `projects_missing_progress` (never zero-filled); empty filtered result → 200 with zeros/None |
| Fields | `snapshot_label` ("April 2026"), `total_projects`, `projects_included`, `projects_missing_progress`, `bins[label,count]`, `mean_progress`, `median_progress`, `agency_filter`, `state_filter` |
| Architecture | Route (`api/dashboard.py`) → Service (`project_service.progress_distribution`) → cached CSV frame → schema (`schemas/dashboard.py`). No ML imports, no risk formulas, no thresholds. |

## 2. Example response (actual, from the running app)

```json
GET /api/dashboard/progress-distribution   → HTTP 200
{
  "snapshot_label": "April 2026",
  "total_projects": 1981,
  "projects_included": 1981,
  "projects_missing_progress": 0,
  "bins": [
    {"label": "0-10", "count": 272},   {"label": "10-20", "count": 124},
    {"label": "20-30", "count": 112},  {"label": "30-40", "count": 119},
    {"label": "40-50", "count": 112},  {"label": "50-60", "count": 130},
    {"label": "60-70", "count": 125},  {"label": "70-80", "count": 169},
    {"label": "80-90", "count": 229},  {"label": "90-100", "count": 589}
  ],
  "mean_progress": 60.21, "median_progress": 70.0,
  "agency_filter": null, "state_filter": null
}
```

Filtered example: `?agency=MoRTH` → 200, total 367 = included 367 =
bin sum 367 (matches the CSV ground truth). Bin counts independently
recomputed from the CSV in the tests — all 10 match exactly.

## 3. Step 3 — preserved endpoints (verified unchanged)

`GET /api/projects/{code}/risk` was **not recreated or modified**; its
contract is asserted by new tests:
- complete row (706724): probabilities/category/status identical to the
  Phase-5 CSV values;
- partial row (612183): `time_overrun_probability` stays **null**, `score_status
  = partial`, `missing_component = time_overrun_probability`, indicators show
  `time_p=n/a`, combined score remains the Phase-5 cost-only value —
  **never converted to zero**;
- `GET /api/risk/summary`: all eight counts re-verified against the
  Phase-5/6 artifacts (1981 / 765 / 575 / 641 / 354 …).

## 4. Test results

`python -m unittest discover -s backend/tests -v` → **Ran 61 tests — OK**
(44 pre-existing tests untouched + **17 new** in
`backend/tests/test_dashboard_graphs.py`):

- all projects included; bin sum == included; 10 labels correct
- full bin-by-bin ground-truth comparison against the CSV (incl. pitfall
  bins 0-10 = 272 and 90-100 = 589, which contain the 95 zeros / 97 100%s)
- boundary values via an injected synthetic frame: 0.0 & 10.0 → "0-10",
  10.0001 → "10-20", 90.0 → "80-90", 90.0001 & 100.0 → "90-100"
- missing-progress handling (counted, excluded from bins, not zero-filled)
- agency filter, state filter, combined filters (counts == CSV truth,
  bin sums == included)
- empty filtered result → 200 with zeros/None (no crash)
- invalid query params (empty / >200 chars) → 422
- preserved risk endpoint + risk summary behaviour (see §3)

No existing test was weakened or deleted.

## 5. Data-integrity status

SHA-256 verified before and after implementation — **all UNCHANGED**:
original CSV, cleaned CSV, feature CSV, cost model, time model, risk CSV,
early-warning CSV. No retraining, no formula/threshold edits; the new code
only reads the cached dataframe.

## 6. Files created/modified

| File | Change |
|---|---|
| `backend/app/api/dashboard.py` | new — 1 GET route |
| `backend/app/schemas/dashboard.py` | new — `ProgressBin`, `ProgressDistributionResponse` |
| `backend/app/services/project_service.py` | added pure `progress_distribution()` (cached frame; injectable frame for boundary tests) |
| `backend/app/schemas/__init__.py` | re-export new schemas |
| `backend/app/main.py` | register `/api/dashboard` router + `ALL_ENDPOINTS` entry |
| `backend/tests/test_dashboard_graphs.py` | new — 17 tests |

## 7. Known limitations

1. Single April 2026 snapshot — `snapshot_label` is fixed; no history/trends.
2. Filters are exact-match strings (181 agencies, 107 states incl. 191
   multi-state rows) — the future UI must handle multi-select/top-N.
3. Missing progress is excluded from mean/median and reported separately
   (currently 0 missing rows in this snapshot).
4. Values outside [0,100] would trip the `sum(bins)==included` assertion
   (loud 500) rather than being silently dropped — Phase-1 cleaning
   guarantees the range, so this cannot occur with the current data.
5. Graph 2 (risk pie) requires **no backend change** — served by the
   existing `/api/projects/{code}/risk`, as confirmed in the audit and now
   contract-tested.
