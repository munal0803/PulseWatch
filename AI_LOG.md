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

This was the first message of the session. The full backend and frontend spec was pasted verbatim:

```
## Backend — Python FastAPI + Firestore

### Requirements
Use these exact packages in requirements.txt:
- fastapi
- uvicorn
- httpx
- apscheduler
- firebase-admin
- python-dotenv
- pydantic
- requests

### Firebase Setup (firebase_client.py)
...
### API Endpoints (routers/monitors.py)
Implement these REST endpoints:
1. POST /monitors ...
2. GET /monitors ...
3. GET /monitors/{monitor_id}/checks ...
4. DELETE /monitors/{monitor_id} ...

### Scheduler (scheduler.py)
- Use APScheduler BackgroundScheduler
- Run ping_all_monitors() every 60 seconds
...

## Frontend — React + Vite + Firestore Real-time
### Firebase Config (src/firebase.js) ...
### App.jsx ...
### AddMonitorForm.jsx ...
### MonitorList.jsx ...
### StatusBadge.jsx ...

## Docker Setup
...
```

**What Claude did:** Generated all 21 files — backend Python modules, React components, Dockerfiles, `docker-compose.yml`, and `.env.example` files — in a single response with parallel file writes.

---

### 2.2 — Architecture documentation

```
create a architecture.md file storing all technical info about this app,
so that LLM can use that file for next queries rather than writing all app again
```

Claude generated [architecture.md](architecture.md) covering the full stack, Firestore schema, every component's props/state, Docker config, and key design decisions — so future sessions don't need the spec re-pasted.

---

### 2.3 — Wiring real Firebase credentials

```
update info const firebaseConfig = {
  apiKey: "AIzaSyCIwZvXpUit9cDC5ENbAw0di-rdfPKhIls",
  authDomain: "assignment-385ae.firebaseapp.com",
  ...
};
```

Claude detected the user had the frontend `.env` open in the IDE and wrote the real values directly into `frontend/.env`, leaving `measurementId` out (Analytics not used).

---

### 2.4 — Unit tests with coverage gate

```
add unit test also with all test covered more then 80%
```

Claude:
- Added `pytest`, `pytest-asyncio`, `pytest-cov` to `requirements.txt`
- Created `tests/conftest.py` with `sys.modules` patching of `firebase_admin` and `apscheduler` before any app import
- Wrote 40 tests across `test_main.py`, `test_monitors.py`, `test_scheduler.py`
- Set `--cov-fail-under=80` in `pytest.ini`

---

### 2.5 — Integration tests against the Firestore Emulator

```
now add integration test
```

Claude created a completely separate `integration_tests/` directory with:
- A custom `_EmulatorCredential` class (subclasses `firebase_admin.credentials.Base`, returns `AnonymousCredentials`) so the emulator works without a real service account
- `autouse` fixture that clears Firestore before/after every test
- 25 API integration tests and 16 scheduler integration tests
- A separate `pytest-integration.ini` so unit and integration runs stay independent

---

### 2.6 — Security and exception-handling audit

```
check if each exception is handled properly,
giving proper error code and it handle gracefully
```

Claude used the `/code-review --fix` skill which:
1. Fanned out **7 parallel sub-agents** (line-by-line scan, removed-behaviour audit, cross-file tracer, reuse, simplification, efficiency, altitude)
2. Collected ~30 raw candidates
3. Ran a **verify pass** to filter CONFIRMED / PLAUSIBLE / REFUTED
4. Applied all 8 confirmed fixes directly to the working tree

---

### 2.7 — Git setup with secret protection

```
how to push this repo in github, take care of key/password
we have added for firebase config
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
pytest: error: unrecognized arguments: --cov-omit=tests/*
fix this
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
fix this  [pasted the pytest failure output]
```

Claude updated both assertions to `"https://example.com/"`.

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

- Pasting the assignment spec as the first prompt
- Copying real Firebase credentials into the chat to wire up `.env`
- Running `pytest` and `docker compose up` to observe real errors
- Typing follow-up prompts when something broke

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
