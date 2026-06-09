# Uptime Monitor — Architecture Reference

## Overview

A full-stack uptime monitoring dashboard. The backend periodically pings registered URLs and writes results to Firestore. The frontend listens to Firestore in real-time via `onSnapshot` — no polling, no websockets.

---

## Stack

| Layer     | Technology                                                  |
|-----------|-------------------------------------------------------------|
| Backend   | Python 3.11, FastAPI, APScheduler, httpx                    |
| Database  | Google Cloud Firestore (via Firebase Admin SDK)             |
| Frontend  | React 18, Vite, Firebase JS SDK v10, date-fns               |
| Container | Docker + Docker Compose                                     |
| Testing   | pytest, pytest-asyncio, pytest-cov (target: ≥80% coverage) |

---

## Repository Layout

```
Assignment/
├── docker-compose.yml
├── serviceAccountKey.json          ← Firebase service account (not committed)
├── architecture.md                 ← this file
├── backend/
│   ├── .env / .env.example
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── firebase_client.py
│   ├── main.py
│   ├── scheduler.py
│   └── routers/
│       ├── __init__.py
│       └── monitors.py
└── frontend/
    ├── .env / .env.example
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── firebase.js
        ├── index.css
        └── components/
            ├── AddMonitorForm.jsx
            ├── MonitorList.jsx
            └── StatusBadge.jsx
```

---

## Backend

### Entry Point — `main.py`
- Creates the FastAPI `app` instance.
- Adds `CORSMiddleware` allowing all origins (`*`) — intentional for local dev.
- Mounts the monitors router at prefix `/api`.
- Uses `@asynccontextmanager` lifespan to start/stop the APScheduler on app boot/shutdown.
- `GET /health` → `{ "status": "ok" }`.

### Firebase Client — `firebase_client.py`
- Initialises `firebase_admin` once using `credentials.Certificate("./serviceAccountKey.json")`.
- Exports a single `db = firestore.client()` used across the app.
- The service account file is mounted read-only via Docker volume.

### Router — `routers/monitors.py`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/monitors` | Create monitor. Body: `{ url, name }`. Validates URL via Pydantic `HttpUrl`. Saves to `monitors` collection. Returns created doc with Firestore ID. |
| `GET` | `/api/monitors` | List all monitors. Returns `id, url, name, lastStatus, lastResponseTime, lastCheckedAt`. |
| `GET` | `/api/monitors/{id}/checks` | Last 20 checks from `monitors/{id}/checks` subcollection, ordered by `checkedAt` DESC. |
| `DELETE` | `/api/monitors/{id}` | Deletes all docs in `checks` subcollection, then deletes the monitor document. |

**Pydantic model:** `MonitorCreate(url: HttpUrl, name: str = "")`.

### Scheduler — `scheduler.py`
- Uses `APScheduler.BackgroundScheduler`.
- Job `ping_monitors` runs `ping_all_monitors()` every **60 seconds**.
- `ping_all_monitors()`:
  1. Streams all docs from `monitors` collection.
  2. Runs `ping_single()` for every monitor concurrently via `asyncio.gather` inside `asyncio.run()`.
- `ping_single(monitor_id, url)`:
  - Calls `ping_url(url)` — `httpx.AsyncClient` GET with **10 s timeout**.
  - On success: `status="up"`, records `statusCode` and `responseTimeMs` (ms, rounded).
  - On any exception (timeout, network error, HTTP error): `status="down"`, both numeric fields `null`.
  - Writes a new doc to `monitors/{id}/checks` with `{ status, statusCode, responseTimeMs, checkedAt }`.
  - Updates parent monitor doc: `lastStatus`, `lastResponseTime`, `lastCheckedAt`.

### Python Dependencies (`requirements.txt`)
```
fastapi, uvicorn, httpx, apscheduler, firebase-admin, python-dotenv, pydantic, requests
```

### Backend Environment (`backend/.env`)
```
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
```

---

## Firestore Data Model

```
monitors/                           ← collection
  {monitor_id}/                     ← document
    url:              string
    name:             string
    createdAt:        timestamp
    lastStatus:       "up" | "down" | null
    lastResponseTime: number | null   (ms)
    lastCheckedAt:    timestamp | null

    checks/                         ← subcollection
      {check_id}/                   ← document
        status:        "up" | "down"
        statusCode:    number | null
        responseTimeMs: number | null
        checkedAt:     timestamp
```

---

## Frontend

### Firebase Init — `src/firebase.js`
- Reads all config from Vite env vars (`VITE_FIREBASE_*`).
- Exports `db = getFirestore(app)` — used directly in components.

### App — `src/App.jsx`
- Registers an `onSnapshot` listener on the `monitors` collection on mount; unsubscribes on unmount.
- State: `monitors[]`, `loading: bool`, `error: string`.
- Renders `<AddMonitorForm />` then `<MonitorList monitors={monitors} />`.
- No polling — all updates come from Firestore push.

### AddMonitorForm — `src/components/AddMonitorForm.jsx`
- Controlled inputs: `url` (required), `name` (optional).
- Validates URL is non-empty before submit; shows inline `field-error`.
- `POST http://localhost:8000/api/monitors` with JSON body.
- Shows success/error feedback below the form row.
- Clears fields on success.

### MonitorList — `src/components/MonitorList.jsx`
- Accepts `monitors[]` prop (from real-time snapshot).
- Sorts: `down` first → `up` → `null/pending`.
- Each card shows: name, URL, `<StatusBadge>`, response time (ms or "—"), relative timestamp via `date-fns/formatDistanceToNow`.
- Handles both Firestore `Timestamp` objects (`.toDate()`) and ISO strings for `lastCheckedAt`.
- Delete button calls `DELETE http://localhost:8000/api/monitors/{id}`.

### StatusBadge — `src/components/StatusBadge.jsx`
- Props: `status: "up" | "down" | null`
- `"up"` → green pill "UP" (`.badge-up`)
- `"down"` → red pill "DOWN" (`.badge-down`)
- `null/undefined` → gray pill "PENDING" (`.badge-pending`)

### Styling — `src/index.css`
- Plain CSS, no framework.
- CSS classes: `.app`, `.app-header`, `.add-form`, `.form-row`, `.form-field`, `.monitor-list`, `.monitor-card`, `.monitor-info`, `.monitor-meta`, `.monitor-name`, `.monitor-url`, `.monitor-rt`, `.monitor-checked`, `.badge`, `.badge-up`, `.badge-down`, `.badge-pending`, `.btn-primary`, `.btn-delete`, `.error-text`, `.success-text`, `.empty-text`.
- Responsive breakpoint at `600px` — card wraps, meta row goes full-width.

### Frontend Dependencies (`package.json`)
```json
"dependencies": {
  "date-fns": "^3.6.0",
  "firebase": "^10.12.2",
  "react": "^18.3.1",
  "react-dom": "^18.3.1"
},
"devDependencies": {
  "@vitejs/plugin-react": "^4.3.1",
  "vite": "^5.3.1"
}
```

### Frontend Environment (`frontend/.env`)
```
VITE_FIREBASE_API_KEY
VITE_FIREBASE_AUTH_DOMAIN
VITE_FIREBASE_PROJECT_ID
VITE_FIREBASE_STORAGE_BUCKET
VITE_FIREBASE_MESSAGING_SENDER_ID
VITE_FIREBASE_APP_ID
```

---

## Docker

### `backend/Dockerfile`
- `python:3.11-slim` → `/app`
- Installs `requirements.txt`, copies source, exposes `8000`.
- CMD: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### `frontend/Dockerfile`
- `node:20-alpine` → `/app`
- Installs deps, copies source, exposes `5173`.
- CMD: `npm run dev -- --host`

### `docker-compose.yml`
```
backend:  port 8000, mounts serviceAccountKey.json (read-only), env_file backend/.env
frontend: port 5173, env_file frontend/.env, depends_on backend
```
Both services use `restart: unless-stopped`.

---

## Running Locally

```bash
# 1. Copy and fill env files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 2. Place Firebase service account at ./serviceAccountKey.json

# 3. Start
docker compose up --build
```

- Frontend: http://localhost:5173  
- Backend API: http://localhost:8000/api  
- Health check: http://localhost:8000/health

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Firestore `onSnapshot` in frontend | Real-time updates without polling or websockets; backend writes trigger instant UI refresh |
| `asyncio.run()` inside APScheduler job | APScheduler runs sync jobs in a thread; `asyncio.run` creates a fresh event loop per tick for async httpx calls |
| Subcollection for checks | Keeps monitor doc lightweight; Firestore subcollections are independently queryable and paginatable |
| Pydantic `HttpUrl` for URL validation | Rejects malformed URLs at the API boundary before any Firestore write |
| Plain CSS (no Tailwind) | Zero build config, sufficient for this scope |
| CORS `allow_origins=["*"]` | Dev convenience; restrict in production |

---

## Testing

### Structure
```
backend/
├── pytest.ini                    ← unit tests (asyncio_mode=auto, cov fail-under=80)
├── pytest-integration.ini        ← integration tests (separate run)
├── tests/                        ← unit tests (all mocked)
│   ├── conftest.py               ← sys.modules mocking + shared fixtures
│   ├── test_main.py              ← health, startup/shutdown, CORS
│   ├── test_monitors.py          ← all 4 REST endpoints, edge cases
│   └── test_scheduler.py         ← ping_url, ping_all_monitors, lifecycle
└── integration_tests/            ← integration tests (real Firestore emulator)
    ├── conftest.py               ← emulator init, db/client fixtures, cleanup
    ├── test_api_integration.py   ← full API→Firestore round-trips
    └── test_scheduler_integration.py  ← scheduler writes to real Firestore
```

### Unit test mocking strategy
Firebase Admin SDK and APScheduler are mocked via `sys.modules` in `tests/conftest.py` **before** any app code is imported.

- `firebase_admin` → `MagicMock` — `firestore.client()` returns a shared `_mock_db`
- `apscheduler.schedulers.background.BackgroundScheduler` → returns `_mock_sched_instance`
- `httpx.AsyncClient` → patched per-test with `AsyncMock`

Both `_mock_db` and `_mock_sched_instance` are reset via an `autouse` fixture between every test.

### Integration test strategy
Uses the **Firebase Firestore Emulator** for real Firestore reads/writes. HTTP is still mocked so tests don't depend on external URLs.

- `_EmulatorCredential` — custom `firebase_admin.credentials.Base` subclass returning `AnonymousCredentials`; emulator ignores auth
- `firebase_client.db`, `scheduler.db`, `routers.monitors.db` patched to point at the emulator client before the FastAPI app is imported
- `APScheduler` instance replaced with `MagicMock` — `ping_all_monitors()` is called manually in tests
- `autouse` fixture clears the `monitors` collection (+ `checks` subcollections) before and after every test

### Running tests
```bash
cd backend

# Unit tests (no external dependencies)
pytest

# Integration tests (requires Firestore emulator)
firebase emulators:start --only firestore --project demo-uptime
pytest -c pytest-integration.ini
```

### Coverage targets
| Module | What's covered |
|--------|----------------|
| `main.py` | health endpoint, lifespan start/stop, CORS |
| `firebase_client.py` | full init path (mocked) |
| `routers/monitors.py` | all 4 endpoints, 404 paths, null timestamp serialisation |
| `scheduler.py` | `ping_url` success/timeout/non-200, `ping_all_monitors` empty/up/down/timeout/multiple, lifecycle |
