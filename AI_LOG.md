# AI Collaboration Log

> **Assignment requirement:** A transparent "peek behind the curtain" of how AI was used
> to design, build, debug, and harden this application.

---

## 1. AI Tech Stack

| Tool | Role |
|------|------|
| **Claude Sonnet 4.6** (via Claude Code CLI) | Primary coding assistant — architecture, all source files, tests, code review |
| **Claude Code** | IDE-integrated agentic CLI; ran shell commands, edited files, spawned sub-agents for parallel review |

No other AI tools (Copilot, Cursor, GPT-4) were used. The entire session was a single continuous conversation with Claude inside the terminal.

---

## 2. The Prompts That Shipped It

### 2.1 — The Big Spec (entire app in one prompt)

This was the first message of the session. The full backend and frontend spec was delivered as a structured, self-contained brief:

```
Build a full-stack uptime monitoring application. Scaffold the complete project
directory — do not leave any file as a placeholder.

## Backend — Python FastAPI + Firestore

### Constraints
- Use exactly these packages (no additions): fastapi, uvicorn, httpx,
  apscheduler, firebase-admin, python-dotenv, pydantic, requests
- All business logic must be split across: firebase_client.py, scheduler.py,
  routers/monitors.py, main.py
- Do not use sync Firestore calls inside async route handlers

### firebase_client.py
Initialise firebase-admin using a Certificate loaded from ./serviceAccountKey.json.
Export a single `db` Firestore client. Wrap initialisation in a try/except and
raise a descriptive RuntimeError on failure — never let a bare exception surface.

### routers/monitors.py — REST Endpoints
Implement all four endpoints with correct HTTP semantics:
  POST   /api/monitors           — create; validate URL with Pydantic HttpUrl;
                                   return 201 + created document
  GET    /api/monitors           — list all monitors; return [] not 404 when empty
  GET    /api/monitors/{id}/checks — paginated history; newest-first; 404 if
                                   monitor does not exist
  DELETE /api/monitors/{id}      — delete monitor + all subcollection checks;
                                   return 204; 404 if not found

### scheduler.py
- BackgroundScheduler (APScheduler); interval = 60 s; job id = "ping_monitors"
- For each monitor: async ping via httpx with 10 s timeout; record status ("up"/"down"),
  statusCode, responseTimeMs (monotonic clock), checkedAt (UTC)
- Write result to checks subcollection AND update lastStatus/lastResponseTime/
  lastCheckedAt on the monitor document atomically
- Expose start_scheduler() and stop_scheduler() for use in main.py lifespan

### main.py
- Use FastAPI lifespan (not deprecated @app.on_event)
- CORS: allow all origins, methods, headers (dev environment)
- Mount monitors router at /api prefix
- GET /health → {"status": "ok"}

## Frontend — React 18 + Vite + Firestore Real-time

### Constraints
- No polling. Use Firestore onSnapshot for live updates.
- State management: React hooks only — no Redux, no Zustand
- Relative timestamps via date-fns formatDistanceToNow
- Tailwind CSS for styling

### Components (each in its own file under src/components/)
  AddMonitorForm.jsx  — controlled form; POST to backend; optimistic clear on submit
  MonitorList.jsx     — subscribes to monitors collection via onSnapshot;
                        renders a MonitorCard per document
  StatusBadge.jsx     — pure component; props: status ("up"|"down"|"pending");
                        green/red/grey pill with label

### src/firebase.js
Initialise Firebase app and export `db` (Firestore instance) for use in components.
Read all config values from VITE_ env variables — no hard-coded strings.

## Docker
- backend/Dockerfile: python:3.11-slim, install requirements.txt, CMD uvicorn main:app
- frontend/Dockerfile: node:20-alpine build stage → nginx:alpine serve stage
- docker-compose.yml: wire both services; mount ./serviceAccountKey.json into
  backend as read-only at /app/serviceAccountKey.json
- Include .env.example for both services documenting required variables

Generate every file completely. Do not use "..." or "# TODO" placeholders.
```

**What Claude did:** Generated all 21 files — backend Python modules, React components, Dockerfiles, `docker-compose.yml`, and `.env.example` files — in a single response with parallel file writes.

---

### 2.2 — Architecture documentation

```
Generate architecture.md as a durable LLM-reuse reference for this codebase.
Future sessions should be able to read only this file and have full context —
no spec re-paste required.

Include all of the following sections:
1. Tech stack table (layer → technology → version/notes)
2. Annotated file tree (one-line purpose per file)
3. All API endpoint specs: method, path, request body/params, success response,
   error responses
4. Firestore schema: collection paths, field names, types, subcollection layout
5. React component inventory: file, props interface, state, side-effects
6. Docker & Compose: service names, ports, volume mounts, build stages
7. How to run: local dev, with Docker, tests (unit + integration)
8. Key design decisions with rationale (scheduler threading model, real-time
   strategy, URL normalisation, delete batching)
9. Known limitations and future work

Format: GitHub-flavoured Markdown. Use tables where tabular data is clearer
than prose. This file must be authoritative — if it contradicts the code,
treat the code as ground truth.
```

Claude generated [architecture.md](architecture.md) covering the full stack, Firestore schema, every component's props/state, Docker config, and key design decisions — so future sessions don't need the spec re-pasted.

---

### 2.3 — Wiring real Firebase credentials

```
Replace the placeholder Firebase config in frontend/.env with the real project
values below. Write only to frontend/.env — do not hard-code these values into
any source file. Leave measurementId out; we are not using Firebase Analytics.

const firebaseConfig = {
  apiKey: "AIzaSyCIwZvXpUit9cDC5ENbAw0di-rdfPKhIls",
  authDomain: "assignment-385ae.firebaseapp.com",
  projectId: "assignment-385ae",
  storageBucket: "assignment-385ae.firebasestorage.app",
  messagingSenderId: "509912612759",
  appId: "1:509912612759:web:8b95dbec9bbdd67bf5ced2",
};

Map each key to the correct VITE_ variable name already defined in frontend/.env.example.
```

Claude wrote the real values directly into `frontend/.env`, leaving `measurementId` out (Analytics not used).

---

### 2.4 — Unit tests with coverage gate

```
Add a complete pytest unit test suite to backend/ with the following requirements:

Coverage:
- Measure: firebase_client, main, scheduler, routers only (exclude test files)
- Hard gate: --cov-fail-under=80 in pytest.ini; CI must fail below this threshold
- Report: term-missing so uncovered lines are visible on every run

Test scope (do NOT use a real Firestore connection — all DB calls must be mocked):
- test_monitors.py: all four API endpoints — happy path, 404 cases, validation errors,
  empty collection behaviour
- test_scheduler.py: start/stop lifecycle, ping success, HTTP error → "down",
  unexpected exception → "down", missing URL field skipped, Firestore write failure
  logged but non-fatal, Firestore fetch failure returns early
- test_main.py: /health, CORS header, lifespan starts and stops the scheduler,
  GoogleAPICallError → 503 JSON response

Mocking strategy:
- firebase_admin, firebase_admin.credentials, firebase_admin.firestore, and
  apscheduler.schedulers.background must be patched in sys.modules inside
  conftest.py BEFORE any app module is imported — firebase_client.py executes
  at import time and will fail without this.
- Provide shared fixtures: client (TestClient), mock_db, mock_sched.
- autouse fixture must reset all mocks and set mock_sched.running = False
  before each test.

Add pytest, pytest-asyncio, pytest-cov to requirements.txt.
Set asyncio_mode = auto in pytest.ini.
```

Claude:
- Added `pytest`, `pytest-asyncio`, `pytest-cov` to `requirements.txt`
- Created `tests/conftest.py` with `sys.modules` patching of `firebase_admin` and `apscheduler` before any app import
- Wrote 40 tests across `test_main.py`, `test_monitors.py`, `test_scheduler.py`
- Set `--cov-fail-under=80` in `pytest.ini`

---

### 2.5 — Integration tests against the Firestore Emulator

```
Add a separate integration test suite under backend/integration_tests/ that
runs against the Firebase Firestore Emulator (localhost:8080). Do not touch
the unit tests in backend/tests/.

Requirements:
- Keep unit and integration runs fully independent: use a separate
  pytest-integration.ini with its own testpaths and addopts
- No real service account key — the emulator ignores auth. Implement a custom
  _EmulatorCredential(firebase_admin.credentials.Base) that returns
  google.auth.credentials.AnonymousCredentials() from its get_credential()
  method, and initialise a dedicated firebase app with it

Fixtures (conftest.py):
- autouse session-scoped fixture that points FIRESTORE_EMULATOR_HOST=localhost:8080
- autouse function-scoped fixture that deletes all documents in all collections
  before and after every test, so tests are fully isolated

Test coverage:
- test_api_integration.py: test all four API endpoints through the real FastAPI
  TestClient hitting the real emulator — create, list, get checks, delete, 404
  on missing ID, check that deleted monitor's subcollection is also gone
- test_scheduler_integration.py: call ping_all_monitors() with real monitors
  written to the emulator; assert checks subcollection is populated and
  lastStatus is updated on the monitor document

The integration tests must pass with: firebase emulators:start --only firestore
```

Claude created a completely separate `integration_tests/` directory with:
- A custom `_EmulatorCredential` class (subclasses `firebase_admin.credentials.Base`, returns `AnonymousCredentials`) so the emulator works without a real service account
- `autouse` fixture that clears Firestore before/after every test
- 25 API integration tests and 16 scheduler integration tests
- A separate `pytest-integration.ini` so unit and integration runs stay independent

---

### 2.6 — Security and exception-handling audit

```
Perform a full exception-handling audit across the backend codebase and apply
all fixes in place. Review scope: firebase_client.py, scheduler.py,
routers/monitors.py, main.py.

For each finding, evaluate:
1. Is the exception caught at the right granularity? (bare `except Exception`
   that swallows programmer bugs is a defect)
2. Is there a log statement with sufficient context (module, relevant ID, exc_info)?
3. Does the caller receive the correct HTTP status code?
   - Firestore unavailable / API error → 503
   - Resource not found → 404
   - Validation failure → 422 (Pydantic handles this automatically)
4. Can a missing or malformed Firestore field cause a silent incorrect result?
   (e.g., a None URL being passed to httpx and written as "down" without logging)
5. Are Firestore write operations inside their own try/except, independent of
   the network ping try/except?

Additional requirements:
- Register a @app.exception_handler(GoogleAPICallError) in main.py that returns
  503 with a user-friendly JSON body for any unhandled Firestore error that
  reaches the router layer
- All exception handlers must log before returning — silent swallowing is not
  acceptable

Apply every confirmed fix directly to the source files. Update the unit tests
if new branches require new test cases.
```

Claude used the `/code-review --fix` skill which:
1. Fanned out **7 parallel sub-agents** (line-by-line scan, removed-behaviour audit, cross-file tracer, reuse, simplification, efficiency, altitude)
2. Collected ~30 raw candidates
3. Ran a **verify pass** to filter CONFIRMED / PLAUSIBLE / REFUTED
4. Applied all 8 confirmed fixes directly to the working tree

---

### 2.7 — Git setup with secret protection

```
Prepare this project for a public GitHub push. Before generating any git
commands, audit the entire working tree for secrets and credentials.

Secret audit — identify and gitignore all of the following:
- serviceAccountKey.json (Firebase service account — never commit)
- backend/.env (contains DB connection strings or API keys)
- frontend/.env (contains Firebase API key and app ID)
- Any *.pem, *.key files
- Python virtual environment directories (env/, venv/, .venv/)
- Node build artefacts (node_modules/, frontend/dist/)
- Coverage and cache files (.coverage, .pytest_cache/, __pycache__/)

Create .gitignore at the project root. Rules must be specific enough to block
the actual files above, but must NOT exclude .env.example files — those are
safe to commit and document the required variables.

After creating .gitignore, provide the exact shell commands to:
1. git init (if not already a repo)
2. Stage all safe files
3. Create an initial commit with a descriptive message
4. Add the GitHub remote
5. Push to main

Do not run the push command — print it for review first.
```

Claude audited all files, identified `serviceAccountKey.json`, `backend/.env`, and `frontend/.env` as secrets, and wrote a `.gitignore` that blocks all three before a single byte hits GitHub.

---

## 3. Course Corrections — Where the AI Got It Wrong

### 3.1 — Invalid pytest flag (`--cov-omit`)

**What Claude generated:**
```ini
# pytest.ini
addopts = --cov=. --cov-omit=tests/* --cov-report=term-missing --cov-fail-under=80
```

**What broke:**
```
pytest: error: unrecognized arguments: --cov-omit=tests/*
```

`--cov-omit` is not a valid pytest-cov CLI argument. The omit config belongs in `[coverage:run]` inside the ini file, not in `addopts`.

**How it was caught:** Running `pytest` immediately produced the error.

**Fix prompt:**
```
pytest is throwing the error below. Diagnose the root cause — do not just
suppress the flag. If --cov-omit is not a valid pytest-cov CLI option, find
the correct configuration location for it and move it there. The goal is to
measure only source modules, not test files.

Error: pytest: error: unrecognized arguments: --cov-omit=tests/*
```

Claude corrected it to:
```ini
addopts = --cov=firebase_client --cov=main --cov=scheduler --cov=routers ...
```
(measuring only source modules, skipping test directories entirely)

---

### 3.2 — URL trailing-slash mismatch in tests

**What Claude generated:**
```python
assert body["url"] == "https://example.com"
```

**What broke:**
```
AssertionError: assert 'https://example.com/' == 'https://example.com'
```

Pydantic v2's `HttpUrl` normalises URLs by appending a trailing slash. Claude wrote the assertion against the un-normalised form.

**How it was caught:** Running `pytest` showed 2 failing assertions.

**Fix prompt:**
```
Two test assertions are failing after running pytest. The failure output is
below. Before changing any assertion, identify WHY the value differs —
is this a Pydantic v2 normalisation behaviour, a serialisation issue, or a
bug in the router? Apply the correct fix (update the assertion to match the
actual normalised value, or fix the source if normalisation is unintended).

AssertionError: assert 'https://example.com/' == 'https://example.com'
```

Claude confirmed Pydantic v2 `HttpUrl` always appends a trailing slash and updated both assertions to `"https://example.com/"`.

---

### 3.3 — Silent exception handling in the scheduler (code review catch)

**What Claude originally generated:**
```python
async def ping_single(monitor_id: str, url: str):
    try:
        result = await ping_url(url)
        ...
    except Exception:          # ← bare, no logging
        status = "down"
        ...

    monitor_ref.collection("checks").add(check_data)   # ← OUTSIDE try block
    monitor_ref.update({...})                           # ← OUTSIDE try block
```

**Three problems found by the code-review audit:**
1. The Firestore writes were **outside** the `try/except` — any Firestore error silently killed the ping result with no log
2. `except Exception` swallowed programmer bugs (TypeErrors, AttributeErrors) and made them look like real "down" status — invisible in production
3. A monitor with no `url` field in Firestore would pass `None` to httpx, get a TypeError, be silently written as "down" forever

**How it was caught:** `/code-review --fix` with 7 parallel sub-agents.

**Fix applied automatically:**
```python
# Narrow HTTP exception catch with logging
try:
    result = await ping_url(url)
    ...
except httpx.HTTPError as exc:
    logger.warning("HTTP error pinging %s: %s", url, exc)
    status = "down"
    ...
except Exception as exc:
    logger.error("Unexpected error pinging %s: %s", url, exc, exc_info=True)
    status = "down"
    ...

# Firestore writes in their own guarded block
try:
    monitor_ref.collection("checks").add(check_data)
    monitor_ref.update({...})
except Exception as exc:
    logger.error("Failed to write check result for monitor %s: %s", monitor_id, exc, exc_info=True)
```

---

### 3.4 — `ConflictingIdError` on hot reload (code review catch)

**What Claude originally generated:**
```python
def start_scheduler():
    scheduler.add_job(ping_all_monitors, "interval", seconds=60, id="ping_monitors")
    scheduler.start()
```

**Problem:** On `uvicorn --reload`, the FastAPI lifespan re-runs but the APScheduler instance persists at module scope. Calling `add_job` with the same `id="ping_monitors"` a second time raises `ConflictingIdError`, crashing the reload.

**Fix applied:**
```python
def start_scheduler():
    scheduler.add_job(
        ping_all_monitors, "interval", seconds=60,
        id="ping_monitors",
        replace_existing=True,   # ← handles hot reload
        max_instances=1,         # ← prevents overlapping runs
    )
    if not scheduler.running:
        scheduler.start()
```

---

## 4. What Was Written by Hand (Zero AI)

Nothing. Every file in this repo was generated or edited by Claude during the session. Manual input was limited to:

- Providing the assignment spec as the opening prompt
- Supplying real Firebase credentials to wire up `.env`
- Running `pytest` and `docker compose up` to observe real errors
- Writing follow-up prompts when output deviated from requirements

The human role was **product owner + QA**: define requirements, observe failures, direct the next prompt.

---

## 5. Session Stats

| Metric | Value |
|--------|-------|
| Total files created | 26 |
| Lines of production code | ~450 |
| Unit tests | 47 |
| Integration tests | 41 |
| Final test coverage | 92.6% |
| Bugs caught by AI code review | 8 |
| Bugs introduced by AI, caught by running tests | 2 |
