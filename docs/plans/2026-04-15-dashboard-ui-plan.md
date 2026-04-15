# AI-IRR Dashboard UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a React + Tailwind web dashboard served by the existing FastAPI app, providing full CRUD management of IRR monitoring targets, prefix inspection, diff history, and ticket tracking.

**Architecture:** Vite-built React SPA mounted at `/app` via FastAPI `StaticFiles`. New backend endpoints extend `api/main.py` using a `SnapshotStore` (SQLite) injected via `app.state`. Targets are managed in-memory (loaded from `config.yaml` on startup, written back on changes). Dockerfile gains a Node.js build stage.

**Tech Stack:** React 18, React Router v6, Tailwind CSS v3, Vite 5, FastAPI `StaticFiles`, Python `SnapshotStore` (existing `app/store.py`).

**Worktree:** `.worktrees/feature/dashboard-ui` (branch `feature/dashboard-ui`). All commands run from this directory.

---

## Task 1: Add pagination + list methods to SnapshotStore

**Files:**
- Modify: `app/store.py` (append new methods at end of `SnapshotStore` class)
- Modify: `tests/test_store.py` (append new tests)

**Step 1: Write the failing tests**

Append to `tests/test_store.py`:
```python
def test_list_snapshots_pagination(tmp_path):
    store = SnapshotStore(str(tmp_path / "test.db"))
    store.migrate()
    for i in range(7):
        store.save_snapshot("AS100", "asn", ["RADB"], [f"10.0.{i}.0/24"], [])
    items, total = store.list_snapshots(page=1, page_size=5)
    assert total == 7
    assert len(items) == 5
    items2, _ = store.list_snapshots(page=2, page_size=5)
    assert len(items2) == 2

def test_list_snapshots_filtered_by_target(tmp_path):
    store = SnapshotStore(str(tmp_path / "test.db"))
    store.migrate()
    store.save_snapshot("AS100", "asn", ["RADB"], ["10.0.0.0/24"], [])
    store.save_snapshot("AS200", "asn", ["RADB"], ["10.1.0.0/24"], [])
    items, total = store.list_snapshots(target="AS100")
    assert total == 1
    assert items[0].target == "AS100"

def test_list_diffs_pagination(tmp_path):
    store = SnapshotStore(str(tmp_path / "test.db"))
    store.migrate()
    for i in range(6):
        sid = store.save_snapshot("AS100", "asn", ["RADB"], [f"10.0.{i}.0/24"], [])
        store.save_diff(sid, None, "AS100", [f"10.0.{i}.0/24"], [], [], [], f"hash{i}")
    items, total = store.list_diffs(page=1, page_size=4)
    assert total == 6
    assert len(items) == 4

def test_list_tickets_pagination(tmp_path):
    store = SnapshotStore(str(tmp_path / "test.db"))
    store.migrate()
    sid = store.save_snapshot("AS100", "asn", ["RADB"], ["10.0.0.0/24"], [])
    diff_id = store.save_diff(sid, None, "AS100", [], [], [], [], "hash0")
    for i in range(3):
        store.save_ticket(diff_id, "AS100", "submitted", {"req": i}, external_ticket_id=f"TKT-{i}")
    items, total = store.list_tickets(page=1, page_size=2)
    assert total == 3
    assert len(items) == 2
```

**Step 2: Run to verify they fail**

```
pytest tests/test_store.py::test_list_snapshots_pagination tests/test_store.py::test_list_snapshots_filtered_by_target tests/test_store.py::test_list_diffs_pagination tests/test_store.py::test_list_tickets_pagination -v
```
Expected: FAIL — `SnapshotStore has no attribute 'list_snapshots'`

**Step 3: Implement the three methods in `app/store.py`**

Add these methods inside the `SnapshotStore` class, after `_row_to_ticket`:

```python
# -------------------------------------------------------------------------
# Paginated list queries (for dashboard API)
# -------------------------------------------------------------------------

def list_snapshots(
    self,
    page: int = 1,
    page_size: int = 25,
    target: Optional[str] = None,
) -> tuple[List[Snapshot], int]:
    """Return a page of snapshots newest-first. Returns (items, total_count)."""
    where = "WHERE target = ?" if target else ""
    params_count = (target,) if target else ()
    total = self.conn.execute(
        f"SELECT COUNT(*) FROM snapshots {where}", params_count
    ).fetchone()[0]
    offset = (page - 1) * page_size
    params = (*params_count, page_size, offset)
    rows = self.conn.execute(
        f"""SELECT * FROM snapshots {where}
            ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    return [self._row_to_snapshot(r) for r in rows], total

def list_diffs(
    self,
    page: int = 1,
    page_size: int = 25,
    target: Optional[str] = None,
) -> tuple[List[Diff], int]:
    """Return a page of diffs newest-first. Returns (items, total_count)."""
    where = "WHERE target = ?" if target else ""
    params_count = (target,) if target else ()
    total = self.conn.execute(
        f"SELECT COUNT(*) FROM diffs {where}", params_count
    ).fetchone()[0]
    offset = (page - 1) * page_size
    params = (*params_count, page_size, offset)
    rows = self.conn.execute(
        f"""SELECT * FROM diffs {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    return [self._row_to_diff(r) for r in rows], total

def list_tickets(
    self,
    page: int = 1,
    page_size: int = 25,
    target: Optional[str] = None,
) -> tuple[List[Ticket], int]:
    """Return a page of tickets newest-first. Returns (items, total_count)."""
    where = "WHERE target = ?" if target else ""
    params_count = (target,) if target else ()
    total = self.conn.execute(
        f"SELECT COUNT(*) FROM tickets {where}", params_count
    ).fetchone()[0]
    offset = (page - 1) * page_size
    params = (*params_count, page_size, offset)
    rows = self.conn.execute(
        f"""SELECT * FROM tickets {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    return [self._row_to_ticket(r) for r in rows], total

def count_open_tickets(self) -> int:
    """Count tickets with status not in ('submitted', 'closed')."""
    return self.conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE status NOT IN ('submitted', 'closed')"
    ).fetchone()[0]

def get_latest_run_at(self) -> Optional[int]:
    """Return the most recent snapshot timestamp across all targets."""
    row = self.conn.execute(
        "SELECT MAX(created_at) FROM snapshots"
    ).fetchone()
    return row[0] if row and row[0] else None

def count_recent_diffs(self, since_timestamp: int) -> int:
    """Count diffs created after the given Unix timestamp."""
    return self.conn.execute(
        "SELECT COUNT(*) FROM diffs WHERE created_at >= ? AND has_changes = 1",
        (since_timestamp,),
    ).fetchone()[0]
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_store.py -v
```
Expected: All store tests pass.

**Step 5: Commit**

```bash
git add app/store.py tests/test_store.py
git commit -m "feat: add paginated list methods to SnapshotStore for dashboard API"
```

---

## Task 2: Add new Pydantic schemas to api/schemas.py

**Files:**
- Modify: `api/schemas.py`

No new tests needed — schemas are validated via endpoint tests in Task 4–6.

**Step 1: Append new schemas to `api/schemas.py`**

```python
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class TargetAddRequest(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^AS(\d+|-[A-Z0-9][-A-Z0-9:]*)$", v):
            raise ValueError(
                "target must be a valid ASN (e.g. AS15169) or AS-SET (e.g. AS-GOOGLE)"
            )
        return v


class TargetInfo(BaseModel):
    name: str
    last_snapshot_at: Optional[int] = None
    ipv4_count: int = 0
    ipv6_count: int = 0


class SnapshotSummary(BaseModel):
    id: int
    target: str
    timestamp: int
    ipv4_count: int
    ipv6_count: int
    created_at: int


class DiffSummary(BaseModel):
    id: int
    target: str
    added_v4: list[str]
    removed_v4: list[str]
    added_v6: list[str]
    removed_v6: list[str]
    has_changes: bool
    created_at: int


class TicketSummary(BaseModel):
    id: int
    target: str
    external_ticket_id: Optional[str]
    status: str
    diff_id: int
    created_at: int


class OverviewResponse(BaseModel):
    total_targets: int
    last_run_at: Optional[int]
    recent_diffs_count: int
    open_tickets_count: int
```

**Step 2: Verify import works**

```
python -c "from api.schemas import PaginatedResponse, OverviewResponse, SnapshotSummary, DiffSummary, TicketSummary, TargetAddRequest, TargetInfo; print('ok')"
```
Expected: `ok`

**Step 3: Commit**

```bash
git add api/schemas.py
git commit -m "feat: add dashboard Pydantic schemas (paginated, overview, targets, diffs, tickets)"
```

---

## Task 3: Wire SnapshotStore into API via app.state

**Files:**
- Modify: `api/settings.py`
- Modify: `api/dependencies.py`
- Modify: `api/main.py` (lifespan only)

**Step 1: Add `db_path` and `config_path` to settings**

In `api/settings.py`, add two fields to the `Settings` class:

```python
db_path: str = "./data/irr.sqlite"
config_path: str = "./config.yaml"
```

**Step 2: Add store and targets dependencies in `api/dependencies.py`**

Replace the entire file contents with:

```python
"""FastAPI dependency injection."""

from fastapi import Request

from app.bgpq4_client import BGPQ4Client
from app.store import SnapshotStore


def get_bgpq4_client(request: Request) -> BGPQ4Client:
    """Retrieve the shared BGPQ4Client instance from app state."""
    return request.app.state.bgpq4_client


def get_store(request: Request) -> SnapshotStore:
    """Retrieve the shared SnapshotStore instance from app state."""
    return request.app.state.store


def get_targets(request: Request) -> list[str]:
    """Retrieve the in-memory targets list from app state."""
    return request.app.state.targets
```

**Step 3: Update the lifespan in `api/main.py` to initialize store and targets**

Replace the `lifespan` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger = logging.getLogger("app")

    # BGPQ4 client
    app.state.bgpq4_client = BGPQ4Client(
        bgpq4_cmd=settings.bgpq4_cmd_list,
        timeout=settings.bgpq4_timeout,
        sources=settings.bgpq4_sources_list,
        aggregate=settings.bgpq4_aggregate,
    )

    # SQLite store
    from app.store import SnapshotStore
    store = SnapshotStore(settings.db_path)
    store.migrate()
    app.state.store = store

    # Targets list: load from config.yaml if present, else empty
    import os
    from pathlib import Path
    targets: list[str] = []
    config_path = Path(settings.config_path)
    if config_path.exists():
        try:
            from app.config import load_config
            cfg = load_config(str(config_path))
            targets = cfg.targets or []
        except Exception:
            pass
    app.state.targets = targets
    app.state.config_path = str(config_path)

    logger.info("IRR Prefix Lookup API started (BGPQ4 + Store)")
    yield

    app.state.bgpq4_client.close()
    store.close()
    logger.info("IRR Prefix Lookup API stopped")
```

**Step 4: Verify app still starts cleanly**

```
python -c "
import asyncio, contextlib
from unittest.mock import patch
with patch('app.bgpq4_client.BGPQ4Client') as m:
    from api.main import app
    print('app imported ok')
"
```
Expected: `app imported ok`

**Step 5: Run existing tests to ensure nothing broke**

```
pytest tests/test_api.py -v
```
Expected: All pass.

**Step 6: Commit**

```bash
git add api/settings.py api/dependencies.py api/main.py
git commit -m "feat: wire SnapshotStore and targets list into API app.state"
```

---

## Task 4: Add target management endpoints

**Files:**
- Modify: `api/main.py` (append new endpoints)
- Modify: `tests/test_api.py` (append new tests)

**Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
def test_get_targets_empty(client):
    """GET /api/v1/targets returns empty list when no targets loaded."""
    response = client.get("/api/v1/targets")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data

def test_add_target(client):
    """POST /api/v1/targets adds a new target."""
    response = client.post("/api/v1/targets", json={"target": "AS15169"})
    assert response.status_code == 201
    assert response.json()["name"] == "AS15169"

def test_add_duplicate_target(client):
    """POST /api/v1/targets with duplicate returns 409."""
    client.post("/api/v1/targets", json={"target": "AS15169"})
    response = client.post("/api/v1/targets", json={"target": "AS15169"})
    assert response.status_code == 409

def test_add_invalid_target(client):
    """POST /api/v1/targets with invalid target returns 422."""
    response = client.post("/api/v1/targets", json={"target": "INVALID"})
    assert response.status_code == 422

def test_delete_target(client):
    """DELETE /api/v1/targets/{target} removes target."""
    client.post("/api/v1/targets", json={"target": "AS15169"})
    response = client.delete("/api/v1/targets/AS15169")
    assert response.status_code == 204
    # Verify gone
    data = client.get("/api/v1/targets").json()
    names = [t["name"] for t in data["items"]]
    assert "AS15169" not in names

def test_delete_nonexistent_target(client):
    """DELETE non-existent target returns 404."""
    response = client.delete("/api/v1/targets/AS99999")
    assert response.status_code == 404
```

**Step 2: Run to verify they fail**

```
pytest tests/test_api.py::test_get_targets_empty tests/test_api.py::test_add_target -v
```
Expected: FAIL — 404 Not Found

**Step 3: Implement target endpoints in `api/main.py`**

Add these imports at the top of `api/main.py` where needed:
```python
from fastapi import Depends, FastAPI, HTTPException, status
```

Append after the existing `get_prefixes` endpoint:

```python
# ---------------------------------------------------------------------------
# Target management endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/targets", tags=["Targets"])
async def list_targets(
    targets: list[str] = Depends(get_targets),
    store: "SnapshotStore" = Depends(get_store),
):
    """List all monitored targets with latest snapshot metadata."""
    from api.schemas import TargetInfo, PaginatedResponse
    items = []
    for t in targets:
        snap = store.get_latest_snapshot(t)
        items.append(TargetInfo(
            name=t,
            last_snapshot_at=snap.timestamp if snap else None,
            ipv4_count=len(snap.ipv4_prefixes) if snap else 0,
            ipv6_count=len(snap.ipv6_prefixes) if snap else 0,
        ))
    return PaginatedResponse(items=items, page=1, page_size=len(items), total=len(items))


@app.post("/api/v1/targets", status_code=201, tags=["Targets"])
async def add_target(
    body: "TargetAddRequest",
    request: Request,
):
    """Add a new monitoring target."""
    from api.schemas import TargetAddRequest, TargetInfo
    target = body.target
    if target in request.app.state.targets:
        raise HTTPException(status_code=409, detail=f"Target {target} already exists")
    request.app.state.targets.append(target)
    return TargetInfo(name=target)


@app.delete("/api/v1/targets/{target}", status_code=204, tags=["Targets"])
async def delete_target(target: str, request: Request):
    """Remove a monitoring target."""
    target = target.upper()
    if target not in request.app.state.targets:
        raise HTTPException(status_code=404, detail=f"Target {target} not found")
    request.app.state.targets.remove(target)
```

Also add to imports at top of `api/main.py`:
```python
from api.schemas import (
    ErrorResponse,
    FetchRequest,
    HealthResponse,
    PrefixResponse,
    TargetAddRequest,
)
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_api.py -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add api/main.py tests/test_api.py
git commit -m "feat: add target management endpoints (GET/POST/DELETE /api/v1/targets)"
```

---

## Task 5: Add history endpoints (snapshots, diffs, tickets)

**Files:**
- Modify: `api/main.py` (append endpoints)
- Modify: `tests/test_api.py` (append tests)

**Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
def test_list_snapshots_empty(client):
    response = client.get("/api/v1/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0

def test_list_snapshots_with_data(client, tmp_db):
    """Seed the store and verify pagination."""
    store = client.app.state.store
    for i in range(3):
        store.save_snapshot("AS100", "asn", ["RADB"], [f"10.0.{i}.0/24"], [])
    response = client.get("/api/v1/snapshots?page=1&page_size=2")
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

def test_list_diffs_empty(client):
    response = client.get("/api/v1/diffs")
    assert response.status_code == 200
    assert response.json()["total"] == 0

def test_list_tickets_empty(client):
    response = client.get("/api/v1/tickets")
    assert response.status_code == 200
    assert response.json()["total"] == 0
```

**Step 2: Run to verify they fail**

```
pytest tests/test_api.py::test_list_snapshots_empty -v
```
Expected: FAIL — 404

**Step 3: Implement history endpoints in `api/main.py`**

Append to `api/main.py`:

```python
# ---------------------------------------------------------------------------
# History endpoints (snapshots, diffs, tickets)
# ---------------------------------------------------------------------------
@app.get("/api/v1/snapshots", tags=["History"])
async def list_snapshots(
    page: int = 1,
    page_size: int = 25,
    target: Optional[str] = None,
    store: "SnapshotStore" = Depends(get_store),
):
    """Paginated snapshot history."""
    from api.schemas import SnapshotSummary, PaginatedResponse
    items, total = store.list_snapshots(page=page, page_size=page_size, target=target)
    summaries = [
        SnapshotSummary(
            id=s.id,
            target=s.target,
            timestamp=s.timestamp,
            ipv4_count=len(s.ipv4_prefixes),
            ipv6_count=len(s.ipv6_prefixes),
            created_at=s.created_at,
        )
        for s in items
    ]
    return PaginatedResponse(items=summaries, page=page, page_size=page_size, total=total)


@app.get("/api/v1/diffs", tags=["History"])
async def list_diffs(
    page: int = 1,
    page_size: int = 25,
    target: Optional[str] = None,
    store: "SnapshotStore" = Depends(get_store),
):
    """Paginated diff history."""
    from api.schemas import DiffSummary, PaginatedResponse
    items, total = store.list_diffs(page=page, page_size=page_size, target=target)
    summaries = [
        DiffSummary(
            id=d.id,
            target=d.target,
            added_v4=d.added_v4,
            removed_v4=d.removed_v4,
            added_v6=d.added_v6,
            removed_v6=d.removed_v6,
            has_changes=d.has_changes,
            created_at=d.created_at,
        )
        for d in items
    ]
    return PaginatedResponse(items=summaries, page=page, page_size=page_size, total=total)


@app.get("/api/v1/tickets", tags=["History"])
async def list_tickets(
    page: int = 1,
    page_size: int = 25,
    target: Optional[str] = None,
    store: "SnapshotStore" = Depends(get_store),
):
    """Paginated ticket history."""
    from api.schemas import TicketSummary, PaginatedResponse
    items, total = store.list_tickets(page=page, page_size=page_size, target=target)
    summaries = [
        TicketSummary(
            id=t.id,
            target=t.target,
            external_ticket_id=t.external_ticket_id,
            status=t.status,
            diff_id=t.diff_id,
            created_at=t.created_at,
        )
        for t in items
    ]
    return PaginatedResponse(items=summaries, page=page, page_size=page_size, total=total)


@app.get("/api/v1/overview", tags=["Dashboard"])
async def get_overview(
    targets: list[str] = Depends(get_targets),
    store: "SnapshotStore" = Depends(get_store),
):
    """Dashboard summary: target count, last run, recent diffs, open tickets."""
    from api.schemas import OverviewResponse
    import time
    since = int(time.time()) - 86400  # last 24 hours
    return OverviewResponse(
        total_targets=len(targets),
        last_run_at=store.get_latest_run_at(),
        recent_diffs_count=store.count_recent_diffs(since),
        open_tickets_count=store.count_open_tickets(),
    )
```

Add `Optional` import at top if not present:
```python
from typing import Optional
```

**Step 4: Run tests**

```
pytest tests/test_api.py -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add api/main.py tests/test_api.py
git commit -m "feat: add snapshots/diffs/tickets/overview history endpoints"
```

---

## Task 6: Scaffold the React frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/index.css`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

**Step 1: Create `frontend/package.json`**

```json
{
  "name": "ai-irr-dashboard",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

**Step 2: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

**Step 3: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: {
    outDir: 'dist',
  },
})
```

**Step 4: Create `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

**Step 5: Create `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

**Step 6: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AI-IRR Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 7: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Step 8: Create `frontend/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename="/app">
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
```

**Step 9: Create a placeholder `frontend/src/App.tsx`**

```tsx
export default function App() {
  return <div className="p-4 text-gray-800">AI-IRR Dashboard loading...</div>
}
```

**Step 10: Install dependencies and verify build**

```bash
cd frontend
npm install
npm run build
```
Expected: `dist/` created with `index.html` and JS/CSS assets.

**Step 11: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat: scaffold React + Tailwind + Vite frontend"
```

---

## Task 7: Build the API client

**Files:**
- Create: `frontend/src/api/client.ts`

**Step 1: Create `frontend/src/api/client.ts`**

```typescript
const BASE = '/api/v1'

export interface TargetInfo {
  name: string
  last_snapshot_at: number | null
  ipv4_count: number
  ipv6_count: number
}

export interface SnapshotSummary {
  id: number
  target: string
  timestamp: number
  ipv4_count: number
  ipv6_count: number
  created_at: number
}

export interface DiffSummary {
  id: number
  target: string
  added_v4: string[]
  removed_v4: string[]
  added_v6: string[]
  removed_v6: string[]
  has_changes: boolean
  created_at: number
}

export interface TicketSummary {
  id: number
  target: string
  external_ticket_id: string | null
  status: string
  diff_id: number
  created_at: number
}

export interface PaginatedResponse<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface OverviewData {
  total_targets: number
  last_run_at: number | null
  recent_diffs_count: number
  open_tickets_count: number
}

export interface HealthData {
  status: string
  version: string
  sources: string[]
}

export interface PrefixData {
  target: string
  ipv4_prefixes: string[]
  ipv6_prefixes: string[]
  ipv4_count: number
  ipv6_count: number
  sources_queried: string[]
  errors: string[]
  query_time_ms: number
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`)
}

export const api = {
  health: () => fetch('/health').then(r => r.json() as Promise<HealthData>),
  overview: () => get<OverviewData>('/overview'),

  targets: {
    list: () => get<PaginatedResponse<TargetInfo>>('/targets'),
    add: (target: string) => post<TargetInfo>('/targets', { target }),
    delete: (target: string) => del(`/targets/${target}`),
  },

  prefixes: {
    get: (target: string) => get<PrefixData>(`/prefixes/${encodeURIComponent(target)}`),
  },

  snapshots: {
    list: (page = 1, pageSize = 25, target?: string) => {
      const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
      if (target) q.set('target', target)
      return get<PaginatedResponse<SnapshotSummary>>(`/snapshots?${q}`)
    },
  },

  diffs: {
    list: (page = 1, pageSize = 25, target?: string) => {
      const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
      if (target) q.set('target', target)
      return get<PaginatedResponse<DiffSummary>>(`/diffs?${q}`)
    },
  },

  tickets: {
    list: (page = 1, pageSize = 25, target?: string) => {
      const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
      if (target) q.set('target', target)
      return get<PaginatedResponse<TicketSummary>>(`/tickets?${q}`)
    },
  },
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors.

**Step 3: Commit**

```bash
cd .. && git add frontend/src/api/
git commit -m "feat: add typed API client for dashboard"
```

---

## Task 8: Build Layout, Sidebar, and App router

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Create `frontend/src/components/Sidebar.tsx`**

```tsx
import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

const NAV = [
  { to: '/', label: 'Overview', icon: '⊞' },
  { to: '/targets', label: 'Targets', icon: '◎' },
  { to: '/prefixes', label: 'Prefixes', icon: '≡' },
  { to: '/diffs', label: 'Diffs', icon: '±' },
  { to: '/tickets', label: 'Tickets', icon: '✎' },
]

export function Sidebar() {
  const [healthy, setHealthy] = useState<boolean | null>(null)

  useEffect(() => {
    const check = () =>
      api.health()
        .then(d => setHealthy(d.status === 'healthy'))
        .catch(() => setHealthy(false))
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <aside className="w-56 min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      <div className="px-4 py-5 border-b border-gray-700 flex items-center gap-2">
        <span
          className={`w-2.5 h-2.5 rounded-full ${
            healthy === null ? 'bg-gray-500' : healthy ? 'bg-green-400' : 'bg-red-500'
          }`}
        />
        <span className="font-bold text-sm tracking-wide">AI-IRR</span>
      </div>
      <nav className="flex-1 py-4">
        {NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`
            }
          >
            <span>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

**Step 2: Create `frontend/src/components/Layout.tsx`**

```tsx
import { ReactNode } from 'react'
import { Sidebar } from './Sidebar'

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 p-6 overflow-auto">{children}</main>
    </div>
  )
}
```

**Step 3: Update `frontend/src/App.tsx` with React Router**

```tsx
import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Overview } from './pages/Overview'
import { Targets } from './pages/Targets'
import { Prefixes } from './pages/Prefixes'
import { Diffs } from './pages/Diffs'
import { Tickets } from './pages/Tickets'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/targets" element={<Targets />} />
        <Route path="/prefixes" element={<Prefixes />} />
        <Route path="/diffs" element={<Diffs />} />
        <Route path="/tickets" element={<Tickets />} />
      </Routes>
    </Layout>
  )
}
```

**Step 4: Create placeholder page files so App compiles**

Create `frontend/src/pages/Overview.tsx`:
```tsx
export function Overview() { return <div>Overview</div> }
```

Create `frontend/src/pages/Targets.tsx`:
```tsx
export function Targets() { return <div>Targets</div> }
```

Create `frontend/src/pages/Prefixes.tsx`:
```tsx
export function Prefixes() { return <div>Prefixes</div> }
```

Create `frontend/src/pages/Diffs.tsx`:
```tsx
export function Diffs() { return <div>Diffs</div> }
```

Create `frontend/src/pages/Tickets.tsx`:
```tsx
export function Tickets() { return <div>Tickets</div> }
```

**Step 5: Verify build**

```bash
cd frontend && npm run build
```
Expected: Clean build, no TypeScript errors.

**Step 6: Commit**

```bash
cd .. && git add frontend/src/
git commit -m "feat: add Layout, Sidebar, and React Router shell"
```

---

## Task 9: Implement Overview page

**Files:**
- Modify: `frontend/src/pages/Overview.tsx`

**Step 1: Replace placeholder with full implementation**

```tsx
import { useEffect, useState } from 'react'
import { api, OverviewData } from '../api/client'

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className="text-3xl font-semibold text-gray-900">{value}</p>
    </div>
  )
}

function formatTs(ts: number | null): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString()
}

export function Overview() {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.overview()
      .then(setData)
      .catch(e => setError(e.message))
  }, [])

  if (error) return <p className="text-red-500">Error: {error}</p>
  if (!data) return <p className="text-gray-400">Loading...</p>

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-6">Overview</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Monitored Targets" value={data.total_targets} />
        <StatCard label="Last Run" value={formatTs(data.last_run_at)} />
        <StatCard label="Recent Diffs (24h)" value={data.recent_diffs_count} />
        <StatCard label="Open Tickets" value={data.open_tickets_count} />
      </div>
    </div>
  )
}
```

**Step 2: Build**

```bash
cd frontend && npm run build
```
Expected: Clean build.

**Step 3: Commit**

```bash
cd .. && git add frontend/src/pages/Overview.tsx
git commit -m "feat: implement Overview page with summary stat cards"
```

---

## Task 10: Implement Targets page

**Files:**
- Modify: `frontend/src/pages/Targets.tsx`

**Step 1: Replace placeholder with full implementation**

```tsx
import { useEffect, useState } from 'react'
import { api, TargetInfo } from '../api/client'

function formatTs(ts: number | null): string {
  if (!ts) return 'Never'
  return new Date(ts * 1000).toLocaleDateString()
}

export function Targets() {
  const [targets, setTargets] = useState<TargetInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newTarget, setNewTarget] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const load = () =>
    api.targets
      .list()
      .then(r => setTargets(r.items))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    setAdding(true)
    setAddError(null)
    try {
      await api.targets.add(newTarget.trim().toUpperCase())
      setNewTarget('')
      await load()
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : 'Failed to add')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (name: string) => {
    if (!confirm(`Remove ${name}?`)) return
    await api.targets.delete(name)
    await load()
  }

  if (loading) return <p className="text-gray-400">Loading...</p>
  if (error) return <p className="text-red-500">Error: {error}</p>

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-6">Targets</h1>

      {/* Add form */}
      <form onSubmit={handleAdd} className="flex gap-2 mb-6">
        <input
          className="border rounded-lg px-3 py-2 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="e.g. AS15169"
          value={newTarget}
          onChange={e => setNewTarget(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={adding}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {adding ? 'Adding…' : 'Add Target'}
        </button>
        {addError && <p className="text-red-500 text-sm self-center">{addError}</p>}
      </form>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Target</th>
              <th className="px-4 py-3 text-right">IPv4</th>
              <th className="px-4 py-3 text-right">IPv6</th>
              <th className="px-4 py-3 text-left">Last Snapshot</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {targets.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                  No targets configured.
                </td>
              </tr>
            )}
            {targets.map(t => (
              <tr key={t.name} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-mono font-semibold text-gray-800">{t.name}</td>
                <td className="px-4 py-3 text-right text-gray-600">{t.ipv4_count}</td>
                <td className="px-4 py-3 text-right text-gray-600">{t.ipv6_count}</td>
                <td className="px-4 py-3 text-gray-500">{formatTs(t.last_snapshot_at)}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => handleDelete(t.name)}
                    className="text-red-500 hover:text-red-700 text-xs"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

**Step 2: Build**

```bash
cd frontend && npm run build
```

**Step 3: Commit**

```bash
cd .. && git add frontend/src/pages/Targets.tsx
git commit -m "feat: implement Targets page with add/remove and prefix counts"
```

---

## Task 11: Implement Prefixes page

**Files:**
- Modify: `frontend/src/pages/Prefixes.tsx`

**Step 1: Replace placeholder**

```tsx
import { useState } from 'react'
import { api, PrefixData } from '../api/client'

export function Prefixes() {
  const [target, setTarget] = useState('')
  const [data, setData] = useState<PrefixData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lookup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!target.trim()) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const result = await api.prefixes.get(target.trim().toUpperCase())
      setData(result)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-6">Prefixes</h1>

      <form onSubmit={lookup} className="flex gap-2 mb-6">
        <input
          className="border rounded-lg px-3 py-2 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="e.g. AS15169"
          value={target}
          onChange={e => setTarget(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Fetching…' : 'Lookup'}
        </button>
      </form>

      {error && <p className="text-red-500 mb-4">{error}</p>}

      {data && (
        <div className="space-y-6">
          <div className="flex gap-4 text-sm text-gray-500">
            <span>IPv4: <strong className="text-gray-800">{data.ipv4_count}</strong></span>
            <span>IPv6: <strong className="text-gray-800">{data.ipv6_count}</strong></span>
            <span>Query: <strong className="text-gray-800">{data.query_time_ms}ms</strong></span>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
              <div className="px-4 py-3 border-b border-gray-100 text-sm font-medium text-gray-700">
                IPv4 Prefixes ({data.ipv4_count})
              </div>
              <div className="max-h-96 overflow-y-auto">
                {data.ipv4_prefixes.map(p => (
                  <div key={p} className="px-4 py-1.5 font-mono text-sm text-gray-700 border-b border-gray-50 last:border-0">
                    {p}
                  </div>
                ))}
                {data.ipv4_prefixes.length === 0 && (
                  <p className="px-4 py-4 text-gray-400 text-sm">None</p>
                )}
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
              <div className="px-4 py-3 border-b border-gray-100 text-sm font-medium text-gray-700">
                IPv6 Prefixes ({data.ipv6_count})
              </div>
              <div className="max-h-96 overflow-y-auto">
                {data.ipv6_prefixes.map(p => (
                  <div key={p} className="px-4 py-1.5 font-mono text-sm text-gray-700 border-b border-gray-50 last:border-0">
                    {p}
                  </div>
                ))}
                {data.ipv6_prefixes.length === 0 && (
                  <p className="px-4 py-4 text-gray-400 text-sm">None</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Build and commit**

```bash
cd frontend && npm run build && cd ..
git add frontend/src/pages/Prefixes.tsx
git commit -m "feat: implement Prefixes lookup page"
```

---

## Task 12: Implement Diffs page

**Files:**
- Modify: `frontend/src/pages/Diffs.tsx`

**Step 1: Replace placeholder**

```tsx
import { useEffect, useState } from 'react'
import { api, DiffSummary } from '../api/client'

function DiffRow({ diff }: { diff: DiffSummary }) {
  const date = new Date(diff.created_at * 1000).toLocaleString()
  const added = diff.added_v4.length + diff.added_v6.length
  const removed = diff.removed_v4.length + diff.removed_v6.length

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 mb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono font-semibold text-gray-800">{diff.target}</span>
        <span className="text-xs text-gray-400">{date}</span>
      </div>
      <div className="flex gap-4 text-sm">
        <span className="text-green-600">+{added} added</span>
        <span className="text-red-500">−{removed} removed</span>
      </div>
      {(diff.added_v4.length > 0 || diff.added_v6.length > 0) && (
        <div className="mt-2 space-y-0.5">
          {[...diff.added_v4, ...diff.added_v6].map(p => (
            <div key={p} className="font-mono text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded">
              + {p}
            </div>
          ))}
        </div>
      )}
      {(diff.removed_v4.length > 0 || diff.removed_v6.length > 0) && (
        <div className="mt-1 space-y-0.5">
          {[...diff.removed_v4, ...diff.removed_v6].map(p => (
            <div key={p} className="font-mono text-xs text-red-700 bg-red-50 px-2 py-0.5 rounded">
              − {p}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function Diffs() {
  const [diffs, setDiffs] = useState<DiffSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const PAGE_SIZE = 10

  useEffect(() => {
    setLoading(true)
    api.diffs
      .list(page, PAGE_SIZE)
      .then(r => { setDiffs(r.items); setTotal(r.total) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  if (loading) return <p className="text-gray-400">Loading...</p>
  if (error) return <p className="text-red-500">Error: {error}</p>

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-2">Diffs</h1>
      <p className="text-sm text-gray-500 mb-6">{total} total changes</p>

      {diffs.length === 0 && (
        <p className="text-gray-400">No diffs recorded yet.</p>
      )}
      {diffs.map(d => <DiffRow key={d.id} diff={d} />)}

      {totalPages > 1 && (
        <div className="flex gap-2 mt-4">
          <button
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-40 hover:bg-gray-50"
          >
            ← Prev
          </button>
          <span className="px-3 py-1.5 text-sm text-gray-500">
            {page} / {totalPages}
          </span>
          <button
            disabled={page === totalPages}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-40 hover:bg-gray-50"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Build and commit**

```bash
cd frontend && npm run build && cd ..
git add frontend/src/pages/Diffs.tsx
git commit -m "feat: implement Diffs page with paginated prefix change history"
```

---

## Task 13: Implement Tickets page

**Files:**
- Modify: `frontend/src/pages/Tickets.tsx`

**Step 1: Replace placeholder**

```tsx
import { useEffect, useState } from 'react'
import { api, TicketSummary } from '../api/client'

const STATUS_COLORS: Record<string, string> = {
  submitted: 'bg-green-100 text-green-700',
  pending: 'bg-yellow-100 text-yellow-700',
  failed: 'bg-red-100 text-red-700',
}

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

export function Tickets() {
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const PAGE_SIZE = 25

  useEffect(() => {
    setLoading(true)
    api.tickets
      .list(page, PAGE_SIZE)
      .then(r => { setTickets(r.items); setTotal(r.total) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  if (loading) return <p className="text-gray-400">Loading...</p>
  if (error) return <p className="text-red-500">Error: {error}</p>

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-2">Tickets</h1>
      <p className="text-sm text-gray-500 mb-6">{total} total tickets</p>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Target</th>
              <th className="px-4 py-3 text-left">Ticket ID</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {tickets.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-400">
                  No tickets yet.
                </td>
              </tr>
            )}
            {tickets.map(t => (
              <tr key={t.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-mono font-semibold text-gray-800">{t.target}</td>
                <td className="px-4 py-3 text-gray-600">{t.external_ticket_id ?? '—'}</td>
                <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                <td className="px-4 py-3 text-gray-500">
                  {new Date(t.created_at * 1000).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex gap-2 mt-4">
          <button
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-40 hover:bg-gray-50"
          >
            ← Prev
          </button>
          <span className="px-3 py-1.5 text-sm text-gray-500">
            {page} / {totalPages}
          </span>
          <button
            disabled={page === totalPages}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-40 hover:bg-gray-50"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Build and commit**

```bash
cd frontend && npm run build && cd ..
git add frontend/src/pages/Tickets.tsx
git commit -m "feat: implement Tickets page with status badges and pagination"
```

---

## Task 14: Mount frontend in FastAPI and update Dockerfile

**Files:**
- Modify: `api/main.py` (add StaticFiles mount)
- Modify: `Dockerfile`
- Create: `frontend/.gitignore`

**Step 1: Add `frontend/dist` to .gitignore**

Create `frontend/.gitignore`:
```
dist/
node_modules/
```

**Step 2: Add StaticFiles mount to `api/main.py`**

Add this import at the top (with other fastapi imports):
```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path
```

Add this block at the end of `api/main.py`, AFTER all endpoint definitions:
```python
# ---------------------------------------------------------------------------
# Serve React frontend (built output) at /app
# ---------------------------------------------------------------------------
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/app", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
```

The `if _frontend_dist.exists()` guard means the API still works in development without a built frontend.

**Step 3: Run tests to verify nothing broke**

```
pytest tests/test_api.py -v
```
Expected: All pass.

**Step 4: Update `Dockerfile`**

Replace the entire Dockerfile with:

```dockerfile
# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Install Python dependencies
FROM python:3.12-slim AS builder
WORKDIR /build
COPY api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 3: Runtime
FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=frontend-builder /frontend/dist ./frontend/dist

COPY app/ ./app/
COPY api/ ./api/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Step 5: Do a local smoke test (no Docker needed)**

Build the frontend and verify the app serves it:
```bash
cd frontend && npm run build && cd ..
uvicorn api.main:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://localhost:8000/app/ | head -5
# Should return HTML with <title>AI-IRR Dashboard</title>
curl -s http://localhost:8000/health
kill %1
```

**Step 6: Commit**

```bash
git add api/main.py Dockerfile frontend/.gitignore
git commit -m "feat: serve React dashboard at /app via FastAPI StaticFiles, update Dockerfile"
```

---

## Task 15: Final verification

**Step 1: Run all tests**

```
pytest tests/ -v
```
Expected: 214+ tests pass (original 214 + new dashboard endpoint tests).

**Step 2: Build frontend**

```bash
cd frontend && npm run build && cd ..
```

**Step 3: Verify the API + dashboard endpoint**

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://localhost:8000/health | python -m json.tool
curl -s http://localhost:8000/api/v1/targets | python -m json.tool
curl -s http://localhost:8000/api/v1/overview | python -m json.tool
# Verify static files
curl -sI http://localhost:8000/app/ | head -3
kill %1
```
Expected: All return valid JSON, `/app/` returns 200 with HTML.

**Step 4: Final commit**

```bash
git add .
git commit -m "chore: final verification pass - dashboard UI complete"
```
