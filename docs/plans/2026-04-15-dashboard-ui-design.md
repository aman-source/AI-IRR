# AI-IRR Dashboard UI — Design Document

**Date:** 2026-04-15
**Status:** Approved
**Stack:** React + Tailwind (Vite) served by FastAPI

---

## Overview

Add a full-CRUD web dashboard to the existing AI-IRR application. The frontend is a React SPA built with Vite and styled with Tailwind CSS. FastAPI serves the built `frontend/dist/` directory as static files at `/app`. No separate service or Docker Compose needed — single container deployment.

---

## Architecture

```
AI-IRR/
├── frontend/              ← new: Vite + React app
│   ├── src/
│   ├── dist/              ← built output (gitignored)
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
├── api/
│   └── main.py            ← extended: new endpoints + StaticFiles mount
└── Dockerfile             ← extended: npm build step added
```

**Serving strategy:** FastAPI mounts `frontend/dist/` at `/app` via `StaticFiles`. The SPA loads at `http://localhost:8000/app`. All API calls go to `/api/v1/*` on the same origin — no CORS issues, no proxy config needed.

---

## Dashboard Pages

Navigation is a left sidebar. `App.tsx` uses React Router v6 with `<Routes>` — each page has its own URL path under `/app/*`.

| Page | Purpose |
|---|---|
| **Overview** | Summary cards: total targets, last run time, recent diff count, open tickets. Health status badge. |
| **Targets** | List all monitored ASNs/AS-SETs. Add new target (modal). Remove target. Trigger on-demand fetch per target. |
| **Prefixes** | Target selector dropdown → display current IPv4 + IPv6 prefixes in sortable table with counts. |
| **Diffs** | Paginated history of prefix changes. Added prefixes in green, removed in red. Filterable by target and date range. |
| **Tickets** | Paginated ticket history with external ticket ID, status badge (open/closed/pending), and linked diff. |

---

## New Backend API Endpoints

Added to `api/main.py` under `/api/v1/`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/targets` | List all configured targets from config |
| `POST` | `/api/v1/targets` | Add a new target |
| `DELETE` | `/api/v1/targets/{target}` | Remove a target |
| `POST` | `/api/v1/targets/{target}/fetch` | Trigger on-demand fetch for one target |
| `GET` | `/api/v1/snapshots` | Paginated snapshot history |
| `GET` | `/api/v1/diffs` | Paginated diff history (filters: target, date) |
| `GET` | `/api/v1/tickets` | Paginated ticket history |
| `POST` | `/api/v1/run` | Trigger full run across all targets |

Existing endpoints (`/health`, `POST /api/v1/fetch`, `GET /api/v1/prefixes/{target}`) are unchanged.

---

## Frontend Component Structure

```
frontend/src/
├── api/
│   └── client.ts          ← typed fetch wrappers for all endpoints
├── pages/
│   ├── Overview.tsx
│   ├── Targets.tsx
│   ├── Prefixes.tsx
│   ├── Diffs.tsx
│   └── Tickets.tsx
├── components/
│   ├── Sidebar.tsx         ← tab buttons + health indicator dot
│   ├── TargetCard.tsx      ← per-ASN card with fetch trigger button
│   ├── PrefixTable.tsx     ← sortable IPv4/IPv6 prefix table
│   ├── DiffRow.tsx         ← added (green) / removed (red) prefix rows
│   ├── TicketBadge.tsx     ← status chip
│   └── LoadingSpinner.tsx
├── hooks/
│   ├── useTargets.ts       ← SWR: /api/v1/targets
│   ├── useDiffs.ts         ← SWR: /api/v1/diffs (paginated)
│   └── useHealth.ts        ← polls /health every 30s
└── App.tsx                 ← React Router v6 <Routes> setup
```

**Data fetching:** Plain `fetch` + `useEffect` with loading/error states. No SWR/React Query dependency.
**Pagination:** Page size 25 for Diffs and Tickets tables.
**Health indicator:** Sidebar header shows a green/red dot, polling `/health` every 30s.
**Stack:** React 18, React Router v6, Tailwind CSS v3, Vite 5.

---

## Dockerfile Changes

Build step added before the Python stage:

```dockerfile
# Frontend build stage
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Python stage (existing)
FROM python:3.12-slim
...
COPY --from=frontend-builder /frontend/dist /app/frontend/dist
```

---

## Implementation Phases

1. **Backend endpoints** — Add 8 new routes to `api/main.py`, wire to `app/store.py` and `app/config.py`
2. **Frontend scaffold** — Vite + React + Tailwind setup in `frontend/`
3. **API client + hooks** — `client.ts` and SWR hooks
4. **Layout + Sidebar** — shell with tab navigation
5. **Pages** — Overview → Targets → Prefixes → Diffs → Tickets
6. **Static file serving** — FastAPI `StaticFiles` mount at `/app`
7. **Dockerfile update** — multi-stage build with Node frontend step
8. **Smoke test** — full build + docker run verification
