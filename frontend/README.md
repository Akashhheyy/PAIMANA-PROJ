# PAIMANA AI — Frontend (Phase 9.2)

React + TypeScript (strict) + Vite dashboard for the PAIMANA AI backend.
Light professional theme intended for an SIH infrastructure-monitoring demo.

## Stack

- Vite 6 + React 18 + TypeScript **strict mode**
- React Router 6 (`/` Overview, `/projects`, `/early-warnings`)
- Recharts (progress bar chart)
- Lucide React icons
- Plain CSS design system (`src/styles/global.css`) — light theme only
- Vitest + Testing Library for tests

## Setup

```powershell
cd frontend
Copy-Item .env.example .env     # VITE_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev                     # http://localhost:5173
```

The backend must be running (it already allows CORS for `localhost:5173`):

```powershell
# from the project root
uvicorn backend.app.main:app --reload --port 8000
```

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | dev server on **port 5173** (strict) |
| `npm run typecheck` | TypeScript type check (strict) |
| `npm run build` | type check + production build to `dist/` |
| `npm test` | Vitest component tests (jsdom) |
| `npm run preview` | preview the production build |

## Structure

```
src/
├── api/          # typed client (fetch) + response types from backend schemas
├── components/   # Layout (sidebar/header), BackendStatus, MetricCard,
│                 # ProgressChart, States (loading/empty/error)
├── pages/        # OverviewPage (functional), ComingSoonPage (nav-only routes)
├── styles/       # global.css light theme
└── test/         # vitest setup + component tests
```

## Data sources (real backend responses only)

- `GET /api/risk/summary` → summary cards (totals, High/Medium/Low, partial
  count, warning totals)
- `GET /api/dashboard/progress-distribution` → pre-binned progress chart
  (all 10 bins, mean/median, "April 2026" snapshot label; missing progress
  excluded, never zero-filled client-side)
- `GET /health` → header connection status (30 s poll)

Types mirror the backend Pydantic schemas field-for-field
(`src/api/types.ts`); nullable fields stay `| null` and are displayed as
"—", never replaced with fake values. **Projects and Early Warnings pages
are navigation placeholders only** in this phase — no fabricated data.
