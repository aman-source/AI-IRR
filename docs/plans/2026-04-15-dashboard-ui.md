# AI-IRR Dashboard UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a React + Tailwind web dashboard served by FastAPI at `/app`, with 5 pages (Overview, Targets, Prefixes, Diffs, Tickets) and 8 new CRUD API endpoints.

**Architecture:** Vite builds `frontend/src/` to `frontend/dist/`. FastAPI mounts `frontend/dist/` as StaticFiles at `/app`. The existing `/api/v1/*` endpoints are extended with paginated list endpoints and targets CRUD. No separate service, no docker-compose — single container.

**Tech Stack:** Python 3.12, FastAPI, React 18, TypeScript, Tailwind CSS 3, Vite 5, SWR 2, SQLite (existing)

---

## Task 1: Add paginated list methods to SnapshotStore

**Files:**
- Modify: `app/store.py`
- Modify: `tests/test_store.py`

**Step 1: Write failing tests**

Add to `tests/test_store.py`:

```python
def test_list_snapshots_empty():
    store = SnapshotStore(":memory:")
    store.migrate()
    rows, total = store.list_snapshots()
    assert rows == []
    assert total == 0

def test_list_snapshots_pagination():
    store = SnapshotStore(":memory:")
    store.migrate()
    for i in range(30):
        store.save_snapshot("AS1", "asn", ["RADB"], [f"10.0.{i}.0/24"], [])
    rows, total = store.list_snapshots(page=1, page_size=25)
    assert len(rows) == 25
    assert total == 30
    rows2, _ = store.list_snapshots(page=2, page_size=25)
    assert len(rows2) == 5

def test_list_snapshots_filter_by_target():
    store = SnapshotStore(":memory:")
    store.migrate()
    store.save_snapshot("AS1", "asn", ["RADB"], ["1.0.0.0/24"], [])
    store.save_snapshot("AS2", "asn", ["RADB"], ["2.0.0.0/24"], [])
    rows, total = store.list_snapshots(target="AS1")
    assert total == 1
    assert rows[0].target == "AS1"

def test_list_diffs_pagination():
    store = SnapshotStore(":memory:")
    store.migrate()
    for i in range(5):
        sid = store.save_snapshot("AS1", "asn", ["RADB"], [f"10.0.{i}.0/24"], [])
        store.save_diff(sid, None, "AS1", [f"10.0.{i}.0/24"], [], [], [], f"hash{i}")
    rows, total = store.list_diffs()
    assert total == 5
    assert len(rows) == 5

def test_list_tickets_pagination():
    store = SnapshotStore(":memory:")
    store.migrate()
    sid = store.save_snapshot("AS1", "asn", ["RADB"], ["1.0.0.0/24"], [])
    did = store.save_diff(sid, None, "AS1", ["1.0.0.0/24"], [], [], [], "h1")
    store.save_ticket(did, "AS1", "submitted", {"key": "val"}, external_ticket_id="T-123")
    rows, total = store.list_tickets()
    assert total == 1
    assert rows[0].external_ticket_id == "T-123"

def test_get_unique_targets():
    store = SnapshotStore(":memory:")
    store.migrate()
    store.save_snapshot("AS1", "asn", ["RADB"], [], [])
    store.save_snapshot("AS2", "asn", ["RADB"], [], [])
    store.save_snapshot("AS1", "asn", ["RADB"], [], [])  # duplicate
    assert store.get_unique_targets() == ["AS1", "AS2"]
```

**Step 2: Run tests to verify they fail**

```
cd c:\Users\ShaikAman\Downloads\AI-IRR
python -m pytest tests/test_store.py::test_list_snapshots_empty tests/test_store.py::test_list_snapshots_pagination tests/test_store.py::test_list_diffs_pagination tests/test_store.py::test_list_tickets_pagination tests/test_store.py::test_get_unique_targets -v
```

Expected: FAIL with `AttributeError: 'SnapshotStore' object has no attribute 'list_snapshots'`

**Step 3: Add methods to SnapshotStore**

Add after `get_snapshot_history` in `app/store.py`:

```python
def list_snapshots(
    self,
    target: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list["Snapshot"], int]:
    """Return paginated snapshots, newest first. Optionally filter by target."""
    offset = (page - 1) * page_size
    if target:
        total = self.conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE target = ?", (target,)
        ).fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM snapshots WHERE target = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (target, page_size, offset),
        ).fetchall()
    else:
        total = self.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
    return [self._row_to_snapshot(r) for r in rows], total
```

Add after `get_latest_diff` in `app/store.py`:

```python
def list_diffs(
    self,
    target: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list["Diff"], int]:
    """Return paginated diffs, newest first. Optionally filter by target."""
    offset = (page - 1) * page_size
    if target:
        total = self.conn.execute(
            "SELECT COUNT(*) FROM diffs WHERE target = ?", (target,)
        ).fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM diffs WHERE target = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (target, page_size, offset),
        ).fetchall()
    else:
        total = self.conn.execute("SELECT COUNT(*) FROM diffs").fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM diffs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
    return [self._row_to_diff(r) for r in rows], total
```

Add after `get_ticket_by_id` in `app/store.py`:

```python
def list_tickets(
    self,
    target: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list["Ticket"], int]:
    """Return paginated tickets, newest first. Optionally filter by target."""
    offset = (page - 1) * page_size
    if target:
        total = self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE target = ?", (target,)
        ).fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM tickets WHERE target = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (target, page_size, offset),
        ).fetchall()
    else:
        total = self.conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
    return [self._row_to_ticket(r) for r in rows], total

def get_unique_targets(self) -> list[str]:
    """Return sorted list of all targets that have snapshots."""
    rows = self.conn.execute(
        "SELECT DISTINCT target FROM snapshots ORDER BY target"
    ).fetchall()
    return [r["target"] for r in rows]
```

**Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_store.py::test_list_snapshots_empty tests/test_store.py::test_list_snapshots_pagination tests/test_store.py::test_list_snapshots_filter_by_target tests/test_store.py::test_list_diffs_pagination tests/test_store.py::test_list_tickets_pagination tests/test_store.py::test_get_unique_targets -v
```

Expected: All PASS

**Step 5: Run full test suite to check for regressions**

```
python -m pytest -v
```

Expected: All existing tests still pass.

**Step 6: Commit**

```bash
git add app/store.py tests/test_store.py
git commit -m "feat: add paginated list methods to SnapshotStore"
```

---

## Task 2: Extend API settings and dependencies

**Files:**
- Modify: `api/settings.py`
- Modify: `api/dependencies.py`

**Step 1: Add db_path and config_path to settings**

In `api/settings.py`, add two fields to the `Settings` class:

```python
irr_db_path: str = "./data/irr.sqlite"
irr_config_path: str = "./config.yaml"
```

The full class becomes:

```python
class Settings(BaseSettings):
    bgpq4_cmd: str = "wsl,bgpq4"
    bgpq4_sources: str = "RADB,RIPE,ARIN,APNIC,LACNIC,AFRINIC,RPKI"
    bgpq4_timeout: int = 120
    bgpq4_aggregate: bool = True
    log_level: str = "INFO"
    cors_origins: str = "*"
    irr_db_path: str = "./data/irr.sqlite"
    irr_config_path: str = "./config.yaml"

    model_config = {"env_prefix": "IRR_API_"}

    @property
    def bgpq4_cmd_list(self) -> list[str]:
        return [s.strip() for s in self.bgpq4_cmd.split(",")]

    @property
    def bgpq4_sources_list(self) -> list[str]:
        return [s.strip() for s in self.bgpq4_sources.split(",") if s.strip()]
```

**Step 2: Add get_store and get_config_targets to dependencies**

Replace the entire `api/dependencies.py` with:

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
```

**Step 3: Update lifespan in api/main.py to create and close the store**

In `api/main.py`, add import at top:

```python
from app.store import SnapshotStore
```

Replace the `lifespan` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    app.state.bgpq4_client = BGPQ4Client(
        bgpq4_cmd=settings.bgpq4_cmd_list,
        timeout=settings.bgpq4_timeout,
        sources=settings.bgpq4_sources_list,
        aggregate=settings.bgpq4_aggregate,
    )
    app.state.store = SnapshotStore(settings.irr_db_path)
    app.state.store.migrate()
    logging.getLogger("app").info("IRR Prefix Lookup API started")
    yield
    app.state.bgpq4_client.close()
    app.state.store.close()
    logging.getLogger("app").info("IRR Prefix Lookup API stopped")
```

**Step 4: Verify the API still starts**

```
uvicorn api.main:app --port 8000
curl http://localhost:8000/health
```

Expected: `{"status":"healthy","version":"2.0.0","sources":[...]}`

**Step 5: Commit**

```bash
git add api/settings.py api/dependencies.py api/main.py
git commit -m "feat: add SnapshotStore to API lifespan and dependency injection"
```

---

## Task 3: Add new API response schemas

**Files:**
- Modify: `api/schemas.py`

**Step 1: Append new models to api/schemas.py**

```python
# ---- Dashboard schemas ----

class TargetItem(BaseModel):
    name: str

class TargetsResponse(BaseModel):
    targets: list[str]

class AddTargetRequest(BaseModel):
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

class SnapshotItem(BaseModel):
    id: int
    target: str
    target_type: str
    timestamp: int
    ipv4_count: int
    ipv6_count: int
    created_at: int

class SnapshotListResponse(BaseModel):
    items: list[SnapshotItem]
    total: int
    page: int
    page_size: int

class DiffItem(BaseModel):
    id: int
    target: str
    added_v4: list[str]
    removed_v4: list[str]
    added_v6: list[str]
    removed_v6: list[str]
    has_changes: bool
    created_at: int

class DiffListResponse(BaseModel):
    items: list[DiffItem]
    total: int
    page: int
    page_size: int

class TicketItem(BaseModel):
    id: int
    diff_id: int
    target: str
    external_ticket_id: Optional[str]
    status: str
    created_at: int

class TicketListResponse(BaseModel):
    items: list[TicketItem]
    total: int
    page: int
    page_size: int

class OverviewStats(BaseModel):
    total_targets: int
    snapshots_total: int
    diffs_total: int
    tickets_total: int
    open_tickets: int
```

**Step 2: Verify schemas import cleanly**

```
python -c "from api.schemas import OverviewStats, DiffListResponse; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add api/schemas.py
git commit -m "feat: add dashboard API schemas"
```

---

## Task 4: Add new CRUD endpoints to FastAPI

**Files:**
- Modify: `api/main.py`

**Step 1: Add imports to api/main.py**

Add to the existing imports block:

```python
import yaml
from pathlib import Path
from fastapi import Query
from api.dependencies import get_store
from api.schemas import (
    # existing...
    AddTargetRequest,
    DiffListResponse, DiffItem,
    OverviewStats,
    SnapshotListResponse, SnapshotItem,
    TargetsResponse,
    TicketListResponse, TicketItem,
)
from app.store import SnapshotStore
```

**Step 2: Add the 8 new endpoint functions**

Add after the existing `get_prefixes` endpoint in `api/main.py`:

```python
# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------

def _load_config_targets() -> list[str]:
    """Read targets list from config.yaml."""
    path = Path(settings.irr_config_path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("targets", [])


def _save_config_targets(targets: list[str]) -> None:
    """Write targets list back to config.yaml, preserving other keys."""
    path = Path(settings.irr_config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}
    raw["targets"] = targets
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)


@app.get("/api/v1/targets", response_model=TargetsResponse, tags=["Dashboard"])
async def list_targets():
    """List all monitored targets from config.yaml."""
    return TargetsResponse(targets=_load_config_targets())


@app.post("/api/v1/targets", response_model=TargetsResponse, tags=["Dashboard"])
async def add_target(body: AddTargetRequest):
    """Add a new target to config.yaml."""
    targets = _load_config_targets()
    if body.target not in targets:
        targets.append(body.target)
        _save_config_targets(targets)
    return TargetsResponse(targets=targets)


@app.delete("/api/v1/targets/{target}", response_model=TargetsResponse, tags=["Dashboard"])
async def remove_target(target: str):
    """Remove a target from config.yaml."""
    target = target.strip().upper()
    targets = [t for t in _load_config_targets() if t != target]
    _save_config_targets(targets)
    return TargetsResponse(targets=targets)


@app.post("/api/v1/targets/{target}/fetch", response_model=PrefixResponse, tags=["Dashboard"])
async def fetch_and_snapshot(
    target: str,
    client: BGPQ4Client = Depends(get_bgpq4_client),
    store: SnapshotStore = Depends(get_store),
):
    """Trigger an on-demand BGPQ4 fetch for a target and save snapshot."""
    try:
        req = FetchRequest(target=target)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    result = await _do_fetch(req.target, client)
    target_type = "asn" if re.match(r"^AS\d+$", req.target) else "as-set"
    await asyncio.to_thread(
        store.save_snapshot,
        req.target, target_type, result.sources_queried,
        result.ipv4_prefixes, result.ipv6_prefixes,
    )
    return result


@app.get("/api/v1/snapshots", response_model=SnapshotListResponse, tags=["Dashboard"])
async def list_snapshots(
    target: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    store: SnapshotStore = Depends(get_store),
):
    """List snapshots with optional target filter and pagination."""
    rows, total = await asyncio.to_thread(store.list_snapshots, target, page, page_size)
    items = [
        SnapshotItem(
            id=s.id, target=s.target, target_type=s.target_type,
            timestamp=s.timestamp,
            ipv4_count=len(s.ipv4_prefixes),
            ipv6_count=len(s.ipv6_prefixes),
            created_at=s.created_at,
        )
        for s in rows
    ]
    return SnapshotListResponse(items=items, total=total, page=page, page_size=page_size)


@app.get("/api/v1/diffs", response_model=DiffListResponse, tags=["Dashboard"])
async def list_diffs(
    target: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    store: SnapshotStore = Depends(get_store),
):
    """List diffs with optional target filter and pagination."""
    rows, total = await asyncio.to_thread(store.list_diffs, target, page, page_size)
    items = [
        DiffItem(
            id=d.id, target=d.target,
            added_v4=d.added_v4, removed_v4=d.removed_v4,
            added_v6=d.added_v6, removed_v6=d.removed_v6,
            has_changes=d.has_changes, created_at=d.created_at,
        )
        for d in rows
    ]
    return DiffListResponse(items=items, total=total, page=page, page_size=page_size)


@app.get("/api/v1/tickets", response_model=TicketListResponse, tags=["Dashboard"])
async def list_tickets(
    target: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    store: SnapshotStore = Depends(get_store),
):
    """List tickets with optional target filter and pagination."""
    rows, total = await asyncio.to_thread(store.list_tickets, target, page, page_size)
    items = [
        TicketItem(
            id=t.id, diff_id=t.diff_id, target=t.target,
            external_ticket_id=t.external_ticket_id,
            status=t.status, created_at=t.created_at,
        )
        for t in rows
    ]
    return TicketListResponse(items=items, total=total, page=page, page_size=page_size)


@app.get("/api/v1/overview", response_model=OverviewStats, tags=["Dashboard"])
async def overview(store: SnapshotStore = Depends(get_store)):
    """Return high-level counts for the overview page."""
    def _stats():
        _, snapshots_total = store.list_snapshots(page_size=1)
        _, diffs_total = store.list_diffs(page_size=1)
        _, tickets_total = store.list_tickets(page_size=1)
        open_count = store.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE status NOT IN ('submitted', 'closed')"
        ).fetchone()[0]
        return dict(
            total_targets=len(store.get_unique_targets()),
            snapshots_total=snapshots_total,
            diffs_total=diffs_total,
            tickets_total=tickets_total,
            open_tickets=open_count,
        )
    stats = await asyncio.to_thread(_stats)
    return OverviewStats(**stats)
```

**Step 3: Verify the API starts and new endpoints appear in docs**

```
uvicorn api.main:app --port 8000
# In browser: http://localhost:8000/docs
# Verify "Dashboard" tag shows all 8 new endpoints
curl http://localhost:8000/api/v1/targets
```

Expected: `{"targets": ["AS15169", "AS16509", "AS8075"]}`

**Step 4: Commit**

```bash
git add api/main.py
git commit -m "feat: add dashboard CRUD endpoints for targets, snapshots, diffs, tickets"
```

---

## Task 5: Scaffold the React frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/App.tsx` (stub)

**Step 1: Create frontend/package.json**

```json
{
  "name": "ai-irr-dashboard",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "swr": "^2.2.5"
  },
  "devDependencies": {
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.41",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.3",
    "vite": "^5.4.1",
    "vitest": "^2.0.5",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "jsdom": "^25.0.0"
  }
}
```

**Step 2: Create frontend/index.html**

```html
<!doctype html>
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

**Step 3: Create frontend/vite.config.ts**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/app/",
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

**Step 4: Create frontend/tailwind.config.js**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

**Step 5: Create frontend/postcss.config.js**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

**Step 6: Create frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

**Step 7: Create frontend/tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

**Step 8: Create frontend/src/index.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Step 9: Create frontend/src/test-setup.ts**

```ts
import "@testing-library/jest-dom";
```

**Step 10: Create stub frontend/src/App.tsx**

```tsx
export default function App() {
  return <div className="p-4 text-gray-900">AI-IRR Dashboard</div>;
}
```

**Step 11: Create frontend/src/main.tsx**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

**Step 12: Install deps and verify build**

```
cd frontend
npm install
npm run build
```

Expected: `dist/` directory created with `index.html` and assets.

**Step 13: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat: scaffold React + Tailwind frontend with Vite"
```

---

## Task 6: Create API client

**Files:**
- Create: `frontend/src/api/client.ts`

**Step 1: Create frontend/src/api/client.ts**

```ts
const BASE = "/api/v1";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---- Types ----

export interface OverviewStats {
  total_targets: number;
  snapshots_total: number;
  diffs_total: number;
  tickets_total: number;
  open_tickets: number;
}

export interface SnapshotItem {
  id: number;
  target: string;
  target_type: string;
  timestamp: number;
  ipv4_count: number;
  ipv6_count: number;
  created_at: number;
}

export interface DiffItem {
  id: number;
  target: string;
  added_v4: string[];
  removed_v4: string[];
  added_v6: string[];
  removed_v6: string[];
  has_changes: boolean;
  created_at: number;
}

export interface TicketItem {
  id: number;
  diff_id: number;
  target: string;
  external_ticket_id: string | null;
  status: string;
  created_at: number;
}

export interface PrefixResponse {
  target: string;
  ipv4_prefixes: string[];
  ipv6_prefixes: string[];
  ipv4_count: number;
  ipv6_count: number;
  sources_queried: string[];
  errors: string[];
  query_time_ms: number;
}

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---- API calls ----

export const api = {
  health: () => apiFetch<{ status: string; version: string; sources: string[] }>("/../../health"),
  overview: () => apiFetch<OverviewStats>("/overview"),
  targets: {
    list: () => apiFetch<{ targets: string[] }>("/targets"),
    add: (target: string) =>
      apiFetch<{ targets: string[] }>("/targets", {
        method: "POST",
        body: JSON.stringify({ target }),
      }),
    remove: (target: string) =>
      apiFetch<{ targets: string[] }>(`/targets/${encodeURIComponent(target)}`, {
        method: "DELETE",
      }),
    fetch: (target: string) =>
      apiFetch<PrefixResponse>(`/targets/${encodeURIComponent(target)}/fetch`, {
        method: "POST",
      }),
  },
  prefixes: (target: string) =>
    apiFetch<PrefixResponse>(`/prefixes/${encodeURIComponent(target)}`),
  snapshots: (params?: { target?: string; page?: number; page_size?: number }) => {
    const q = new URLSearchParams();
    if (params?.target) q.set("target", params.target);
    if (params?.page) q.set("page", String(params.page));
    if (params?.page_size) q.set("page_size", String(params.page_size));
    return apiFetch<PagedResponse<SnapshotItem>>(`/snapshots?${q}`);
  },
  diffs: (params?: { target?: string; page?: number; page_size?: number }) => {
    const q = new URLSearchParams();
    if (params?.target) q.set("target", params.target);
    if (params?.page) q.set("page", String(params.page));
    if (params?.page_size) q.set("page_size", String(params.page_size));
    return apiFetch<PagedResponse<DiffItem>>(`/diffs?${q}`);
  },
  tickets: (params?: { target?: string; page?: number; page_size?: number }) => {
    const q = new URLSearchParams();
    if (params?.target) q.set("target", params.target);
    if (params?.page) q.set("page", String(params.page));
    if (params?.page_size) q.set("page_size", String(params.page_size));
    return apiFetch<PagedResponse<TicketItem>>(`/tickets?${q}`);
  },
};
```

**Step 2: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add typed API client for dashboard endpoints"
```

---

## Task 7: Create SWR hooks

**Files:**
- Create: `frontend/src/hooks/useHealth.ts`
- Create: `frontend/src/hooks/useOverview.ts`
- Create: `frontend/src/hooks/useTargets.ts`
- Create: `frontend/src/hooks/useDiffs.ts`
- Create: `frontend/src/hooks/useTickets.ts`

**Step 1: Create frontend/src/hooks/useHealth.ts**

```ts
import useSWR from "swr";
import { api } from "../api/client";

export function useHealth() {
  const { data, error } = useSWR("health", api.health, {
    refreshInterval: 30_000,
  });
  return {
    healthy: data?.status === "healthy",
    version: data?.version,
    isLoading: !data && !error,
  };
}
```

**Step 2: Create frontend/src/hooks/useOverview.ts**

```ts
import useSWR from "swr";
import { api } from "../api/client";

export function useOverview() {
  const { data, error, isLoading } = useSWR("overview", api.overview, {
    refreshInterval: 60_000,
  });
  return { data, error, isLoading };
}
```

**Step 3: Create frontend/src/hooks/useTargets.ts**

```ts
import useSWR, { mutate } from "swr";
import { api } from "../api/client";

export function useTargets() {
  const { data, error, isLoading } = useSWR("targets", api.targets.list);
  return {
    targets: data?.targets ?? [],
    error,
    isLoading,
    addTarget: async (target: string) => {
      await api.targets.add(target);
      mutate("targets");
    },
    removeTarget: async (target: string) => {
      await api.targets.remove(target);
      mutate("targets");
    },
    fetchTarget: (target: string) => api.targets.fetch(target),
  };
}
```

**Step 4: Create frontend/src/hooks/useDiffs.ts**

```ts
import useSWR from "swr";
import { api } from "../api/client";

export function useDiffs(target?: string, page = 1) {
  const key = ["diffs", target, page];
  const { data, error, isLoading } = useSWR(key, () =>
    api.diffs({ target, page, page_size: 25 })
  );
  return { data, error, isLoading };
}
```

**Step 5: Create frontend/src/hooks/useTickets.ts**

```ts
import useSWR from "swr";
import { api } from "../api/client";

export function useTickets(target?: string, page = 1) {
  const key = ["tickets", target, page];
  const { data, error, isLoading } = useSWR(key, () =>
    api.tickets({ target, page, page_size: 25 })
  );
  return { data, error, isLoading };
}
```

**Step 6: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add SWR hooks for dashboard data fetching"
```

---

## Task 8: Build Sidebar and App shell

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Create frontend/src/components/Sidebar.tsx**

```tsx
import { useHealth } from "../hooks/useHealth";

type Page = "overview" | "targets" | "prefixes" | "diffs" | "tickets";

interface Props {
  active: Page;
  onChange: (p: Page) => void;
}

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "⬛" },
  { id: "targets", label: "Targets", icon: "🎯" },
  { id: "prefixes", label: "Prefixes", icon: "🔀" },
  { id: "diffs", label: "Diffs", icon: "📊" },
  { id: "tickets", label: "Tickets", icon: "🎫" },
];

export function Sidebar({ active, onChange }: Props) {
  const { healthy, isLoading } = useHealth();
  const dot = isLoading
    ? "bg-gray-400"
    : healthy
    ? "bg-green-500"
    : "bg-red-500";

  return (
    <aside className="w-52 min-h-screen bg-gray-900 text-white flex flex-col">
      <div className="px-4 py-5 flex items-center gap-2 border-b border-gray-700">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${dot}`} />
        <span className="font-bold text-sm tracking-wide">AI-IRR</span>
      </div>
      <nav className="flex-1 py-4">
        {NAV.map((item) => (
          <button
            key={item.id}
            onClick={() => onChange(item.id)}
            className={`w-full text-left px-4 py-2.5 text-sm flex items-center gap-3 transition-colors ${
              active === item.id
                ? "bg-blue-600 text-white"
                : "text-gray-300 hover:bg-gray-800"
            }`}
          >
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
```

**Step 2: Replace frontend/src/App.tsx**

```tsx
import { useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./pages/Overview";
import { Targets } from "./pages/Targets";
import { Prefixes } from "./pages/Prefixes";
import { Diffs } from "./pages/Diffs";
import { Tickets } from "./pages/Tickets";

type Page = "overview" | "targets" | "prefixes" | "diffs" | "tickets";

export default function App() {
  const [page, setPage] = useState<Page>("overview");

  const content = {
    overview: <Overview />,
    targets: <Targets />,
    prefixes: <Prefixes />,
    diffs: <Diffs />,
    tickets: <Tickets />,
  }[page];

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <Sidebar active={page} onChange={setPage} />
      <main className="flex-1 p-6 overflow-auto">{content}</main>
    </div>
  );
}
```

**Step 3: Create stub page files** (so TypeScript compiles while building pages incrementally)

Create `frontend/src/pages/Overview.tsx`:
```tsx
export function Overview() { return <div>Overview</div>; }
```

Create `frontend/src/pages/Targets.tsx`:
```tsx
export function Targets() { return <div>Targets</div>; }
```

Create `frontend/src/pages/Prefixes.tsx`:
```tsx
export function Prefixes() { return <div>Prefixes</div>; }
```

Create `frontend/src/pages/Diffs.tsx`:
```tsx
export function Diffs() { return <div>Diffs</div>; }
```

Create `frontend/src/pages/Tickets.tsx`:
```tsx
export function Tickets() { return <div>Tickets</div>; }
```

**Step 4: Build to verify TypeScript compiles**

```
cd frontend
npm run build
```

Expected: Build succeeds, no TypeScript errors.

**Step 5: Commit**

```bash
cd ..
git add frontend/src/
git commit -m "feat: add Sidebar and App shell with tab navigation"
```

---

## Task 9: Overview page

**Files:**
- Modify: `frontend/src/pages/Overview.tsx`

**Step 1: Implement Overview.tsx**

```tsx
import { useOverview } from "../hooks/useOverview";

interface StatCardProps {
  label: string;
  value: number | string;
  color: string;
}

function StatCard({ label, value, color }: StatCardProps) {
  return (
    <div className={`rounded-lg p-5 text-white ${color} shadow`}>
      <p className="text-sm font-medium opacity-80">{label}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
    </div>
  );
}

export function Overview() {
  const { data, isLoading, error } = useOverview();

  if (isLoading) return <p className="text-gray-500">Loading…</p>;
  if (error) return <p className="text-red-600">Failed to load overview.</p>;
  if (!data) return null;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Overview</h1>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard label="Targets" value={data.total_targets} color="bg-blue-600" />
        <StatCard label="Snapshots" value={data.snapshots_total} color="bg-indigo-600" />
        <StatCard label="Diffs" value={data.diffs_total} color="bg-purple-600" />
        <StatCard label="Tickets" value={data.tickets_total} color="bg-gray-700" />
        <StatCard label="Open Tickets" value={data.open_tickets} color="bg-orange-500" />
      </div>
    </div>
  );
}
```

**Step 2: Build to verify**

```
cd frontend && npm run build
```

**Step 3: Commit**

```bash
cd ..
git add frontend/src/pages/Overview.tsx
git commit -m "feat: implement Overview page with stat cards"
```

---

## Task 10: Targets page

**Files:**
- Modify: `frontend/src/pages/Targets.tsx`

**Step 1: Implement Targets.tsx**

```tsx
import { useState } from "react";
import { useTargets } from "../hooks/useTargets";

export function Targets() {
  const { targets, isLoading, error, addTarget, removeTarget, fetchTarget } = useTargets();
  const [newTarget, setNewTarget] = useState("");
  const [addError, setAddError] = useState("");
  const [fetchingTarget, setFetchingTarget] = useState<string | null>(null);

  const handleAdd = async () => {
    setAddError("");
    try {
      await addTarget(newTarget.trim());
      setNewTarget("");
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Failed to add target");
    }
  };

  const handleFetch = async (target: string) => {
    setFetchingTarget(target);
    try {
      await fetchTarget(target);
    } finally {
      setFetchingTarget(null);
    }
  };

  if (isLoading) return <p className="text-gray-500">Loading…</p>;
  if (error) return <p className="text-red-600">Failed to load targets.</p>;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Targets</h1>

      {/* Add target */}
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={newTarget}
          onChange={(e) => setNewTarget(e.target.value)}
          placeholder="AS15169 or AS-GOOGLE"
          className="border border-gray-300 rounded px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <button
          onClick={handleAdd}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 transition"
        >
          Add Target
        </button>
      </div>
      {addError && <p className="text-red-600 text-sm mb-4">{addError}</p>}

      {/* Target list */}
      {targets.length === 0 ? (
        <p className="text-gray-400">No targets configured. Add one above.</p>
      ) : (
        <div className="space-y-2">
          {targets.map((t) => (
            <div
              key={t}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm"
            >
              <span className="font-mono text-sm font-medium text-gray-800">{t}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => handleFetch(t)}
                  disabled={fetchingTarget === t}
                  className="text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 rounded px-3 py-1 hover:bg-indigo-100 disabled:opacity-50 transition"
                >
                  {fetchingTarget === t ? "Fetching…" : "Fetch Now"}
                </button>
                <button
                  onClick={() => removeTarget(t)}
                  className="text-xs bg-red-50 text-red-600 border border-red-200 rounded px-3 py-1 hover:bg-red-100 transition"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Targets.tsx
git commit -m "feat: implement Targets page with add/remove/fetch"
```

---

## Task 11: Prefixes page

**Files:**
- Modify: `frontend/src/pages/Prefixes.tsx`

**Step 1: Implement Prefixes.tsx**

```tsx
import { useState } from "react";
import useSWR from "swr";
import { api } from "../api/client";
import { useTargets } from "../hooks/useTargets";

export function Prefixes() {
  const { targets } = useTargets();
  const [selected, setSelected] = useState("");

  const { data, isLoading, error } = useSWR(
    selected ? ["prefixes", selected] : null,
    () => api.prefixes(selected)
  );

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Prefixes</h1>

      <div className="mb-6">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="border border-gray-300 rounded px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">-- Select a target --</option>
          {targets.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {!selected && <p className="text-gray-400">Select a target to view its prefixes.</p>}
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">Failed to fetch prefixes.</p>}

      {data && (
        <div className="space-y-6">
          {/* IPv4 */}
          <section>
            <h2 className="text-lg font-medium text-gray-700 mb-2">
              IPv4 Prefixes <span className="text-sm text-gray-400">({data.ipv4_count})</span>
            </h2>
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600 text-left">
                  <tr>
                    <th className="px-4 py-2 font-medium">Prefix</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ipv4_prefixes.map((p) => (
                    <tr key={p} className="border-t border-gray-100">
                      <td className="px-4 py-2 font-mono">{p}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.ipv4_prefixes.length === 0 && (
                <p className="text-gray-400 px-4 py-3 text-sm">No IPv4 prefixes.</p>
              )}
            </div>
          </section>

          {/* IPv6 */}
          <section>
            <h2 className="text-lg font-medium text-gray-700 mb-2">
              IPv6 Prefixes <span className="text-sm text-gray-400">({data.ipv6_count})</span>
            </h2>
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600 text-left">
                  <tr>
                    <th className="px-4 py-2 font-medium">Prefix</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ipv6_prefixes.map((p) => (
                    <tr key={p} className="border-t border-gray-100">
                      <td className="px-4 py-2 font-mono">{p}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.ipv6_prefixes.length === 0 && (
                <p className="text-gray-400 px-4 py-3 text-sm">No IPv6 prefixes.</p>
              )}
            </div>
          </section>

          <p className="text-xs text-gray-400">
            Sources: {data.sources_queried.join(", ")} · {data.query_time_ms}ms
          </p>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Prefixes.tsx
git commit -m "feat: implement Prefixes page with target selector and prefix tables"
```

---

## Task 12: Diffs page

**Files:**
- Modify: `frontend/src/pages/Diffs.tsx`
- Create: `frontend/src/components/DiffRow.tsx`

**Step 1: Create frontend/src/components/DiffRow.tsx**

```tsx
import type { DiffItem } from "../api/client";

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

export function DiffRow({ diff }: { diff: DiffItem }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-sm font-semibold text-gray-800">{diff.target}</span>
        <span className="text-xs text-gray-400">{fmt(diff.created_at)}</span>
        {!diff.has_changes && (
          <span className="text-xs text-gray-400 italic">No changes</span>
        )}
      </div>
      {diff.has_changes && (
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            {diff.added_v4.map((p) => (
              <div key={p} className="text-green-700 font-mono">+ {p}</div>
            ))}
            {diff.added_v6.map((p) => (
              <div key={p} className="text-green-700 font-mono">+ {p}</div>
            ))}
          </div>
          <div>
            {diff.removed_v4.map((p) => (
              <div key={p} className="text-red-600 font-mono">− {p}</div>
            ))}
            {diff.removed_v6.map((p) => (
              <div key={p} className="text-red-600 font-mono">− {p}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Implement Diffs.tsx**

```tsx
import { useState } from "react";
import { useDiffs } from "../hooks/useDiffs";
import { useTargets } from "../hooks/useTargets";
import { DiffRow } from "../components/DiffRow";

export function Diffs() {
  const { targets } = useTargets();
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useDiffs(filter || undefined, page);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Diffs</h1>

      <div className="flex gap-2 mb-4">
        <select
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
          className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All targets</option>
          {targets.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="text-sm text-gray-500 self-center">
          {data ? `${data.total} total` : ""}
        </span>
      </div>

      {isLoading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">Failed to load diffs.</p>}

      {data && (
        <>
          {data.items.length === 0 ? (
            <p className="text-gray-400">No diffs recorded yet.</p>
          ) : (
            <div className="space-y-3">
              {data.items.map((d) => <DiffRow key={d.id} diff={d} />)}
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border rounded text-sm disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-sm self-center text-gray-600">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 border rounded text-sm disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/src/pages/Diffs.tsx frontend/src/components/DiffRow.tsx
git commit -m "feat: implement Diffs page with paginated diff history"
```

---

## Task 13: Tickets page

**Files:**
- Modify: `frontend/src/pages/Tickets.tsx`
- Create: `frontend/src/components/TicketBadge.tsx`

**Step 1: Create frontend/src/components/TicketBadge.tsx**

```tsx
const STATUS_STYLES: Record<string, string> = {
  submitted: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-600",
  pending: "bg-yellow-100 text-yellow-800",
  failed: "bg-red-100 text-red-800",
};

export function TicketBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status.toLowerCase()] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
```

**Step 2: Implement Tickets.tsx**

```tsx
import { useState } from "react";
import { useTickets } from "../hooks/useTickets";
import { useTargets } from "../hooks/useTargets";
import { TicketBadge } from "../components/TicketBadge";

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

export function Tickets() {
  const { targets } = useTargets();
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useTickets(filter || undefined, page);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Tickets</h1>

      <div className="flex gap-2 mb-4">
        <select
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
          className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All targets</option>
          {targets.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="text-sm text-gray-500 self-center">
          {data ? `${data.total} total` : ""}
        </span>
      </div>

      {isLoading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">Failed to load tickets.</p>}

      {data && (
        <>
          {data.items.length === 0 ? (
            <p className="text-gray-400">No tickets recorded yet.</p>
          ) : (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600 text-left">
                  <tr>
                    <th className="px-4 py-3 font-medium">Target</th>
                    <th className="px-4 py-3 font-medium">Ticket ID</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Diff</th>
                    <th className="px-4 py-3 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((t) => (
                    <tr key={t.id} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono font-medium">{t.target}</td>
                      <td className="px-4 py-3 font-mono text-blue-700">
                        {t.external_ticket_id ?? "—"}
                      </td>
                      <td className="px-4 py-3"><TicketBadge status={t.status} /></td>
                      <td className="px-4 py-3 text-gray-500">#{t.diff_id}</td>
                      <td className="px-4 py-3 text-gray-500">{fmt(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border rounded text-sm disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-sm self-center text-gray-600">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 border rounded text-sm disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

**Step 3: Final build**

```
cd frontend && npm run build
```

Expected: Build succeeds with no TypeScript errors.

**Step 4: Commit**

```bash
cd ..
git add frontend/src/pages/Tickets.tsx frontend/src/components/TicketBadge.tsx
git commit -m "feat: implement Tickets page with status badges and pagination"
```

---

## Task 14: Mount static files in FastAPI

**Files:**
- Modify: `api/main.py`

**Step 1: Add StaticFiles mount after all endpoint definitions**

Add imports at top of `api/main.py`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
```

Add at the **end** of `api/main.py` (after all endpoints):

```python
# Serve the React dashboard — must be last so API routes take precedence
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/app", StaticFiles(directory=_frontend_dist, html=True), name="dashboard")
```

**Step 2: Build frontend and start server**

```
cd frontend && npm run build && cd ..
uvicorn api.main:app --port 8000
```

**Step 3: Verify dashboard loads**

Open `http://localhost:8000/app/` in a browser.
Expected: AI-IRR dashboard loads with sidebar and Overview page.

**Step 4: Verify API still works**

```
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/targets
```

**Step 5: Commit**

```bash
git add api/main.py
git commit -m "feat: mount React frontend as StaticFiles at /app"
```

---

## Task 15: Update Dockerfile with Node build stage

**Files:**
- Modify: `Dockerfile`

**Step 1: Replace Dockerfile**

```dockerfile
# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Install Python deps
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

RUN mkdir -p data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Step 2: Build the Docker image**

```
docker build -t ai-irr-dashboard .
```

Expected: Build completes, Node stage builds frontend, Python stage copies it in.

**Step 3: Run and verify**

```
docker run -p 8000:8000 ai-irr-dashboard
curl http://localhost:8000/health
# Open http://localhost:8000/app/ in browser
```

Expected: Dashboard loads inside Docker.

**Step 4: Commit**

```bash
git add Dockerfile
git commit -m "feat: add Node frontend build stage to Dockerfile"
```

---

## Task 16: End-to-end smoke test

**Step 1: Start server with a real database**

```
IRR_API_IRR_DB_PATH=./data/irr.sqlite uvicorn api.main:app --port 8000
```

**Step 2: Run smoke checks**

```bash
# Health
curl -s http://localhost:8000/health | python -m json.tool

# Targets from config.yaml
curl -s http://localhost:8000/api/v1/targets | python -m json.tool

# Add a target
curl -s -X POST http://localhost:8000/api/v1/targets \
  -H "Content-Type: application/json" \
  -d '{"target": "AS64496"}' | python -m json.tool

# Remove it
curl -s -X DELETE http://localhost:8000/api/v1/targets/AS64496 | python -m json.tool

# Overview stats
curl -s http://localhost:8000/api/v1/overview | python -m json.tool

# Diffs (will be empty initially)
curl -s "http://localhost:8000/api/v1/diffs?page=1&page_size=10" | python -m json.tool
```

**Step 3: Open dashboard in browser**

Go to `http://localhost:8000/app/`
- Verify sidebar shows 5 tabs
- Verify Overview shows stat cards
- Verify Targets page shows targets from config.yaml
- Verify Diffs and Tickets pages show empty state

**Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: smoke test corrections"
```
