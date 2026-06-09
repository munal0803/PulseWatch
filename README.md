# PulseWatch

PulseWatch is a lightweight uptime monitoring platform built with React, Python (FastAPI), Firebase, and Docker. It periodically checks registered URLs, tracks response times and status codes, stores health data, and provides a real-time dashboard showing whether services are up or down.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Firebase SDK |
| Backend | Python, FastAPI, APScheduler |
| Database | Firebase Firestore |
| Auth | Firebase Authentication |
| Containerization | Docker, Docker Compose |

---

## Prerequisites

Make sure you have the following installed:

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- Git

That's it — no need to install Node.js or Python separately when using Docker.

---

## Setup & Run

### Step 1 — Clone the repository

```bash
git clone https://github.com/munal0803/PulseWatch.git
cd PulseWatch
```

### Step 2 — Add the Firebase service account key

You should have received a file called `serviceAccountKey.json` shared separately (via email / drive / message).

Place it in the **root of the project** (same level as `docker-compose.yml`):

```
PulseWatch/
├── serviceAccountKey.json   ← place it here
├── docker-compose.yml
├── backend/
└── frontend/
```

> This file gives the backend admin access to Firestore. Without it, the backend will not start.

### Step 3 — Verify environment files

The `.env` files are already included in the repo with the correct Firebase config. You do **not** need to change anything.

```
backend/.env      ← already configured
frontend/.env     ← already configured
```

If for any reason they are missing, copy from the examples and fill in the values from your Firebase project:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

### Step 4 — Start the application

```bash
docker-compose up --build
```

Docker will:
1. Build the backend FastAPI image
2. Build the frontend Vite/React image
3. Start both services

First build takes 2–3 minutes. Subsequent starts are faster.

### Step 5 — Open the app

| Service | URL |
|---------|-----|
| Frontend (React app) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

---

## Stopping the app

```bash
# Stop containers
docker-compose down

# Stop and remove volumes (full reset)
docker-compose down -v
```

---

## Running Without Docker (Optional)

If you prefer running services directly:

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend** (in a separate terminal):
```bash
cd frontend
npm install
npm run dev
```

> Make sure `serviceAccountKey.json` is in the project root and `backend/.env` has `GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json`.

---

## Project Structure

```
PulseWatch/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── scheduler.py         # APScheduler — runs URL checks periodically
│   ├── routers/
│   │   └── monitors.py      # API routes for monitors
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── firebase.js      # Firebase SDK initialization
│   │   └── components/
│   ├── package.json
│   ├── Dockerfile
│   └── .env
├── docker-compose.yml
├── serviceAccountKey.json   # ← not in repo, shared separately
└── README.md
```

---

## Troubleshooting

**Backend fails to start / Firestore errors**
- Make sure `serviceAccountKey.json` is in the project root
- Check the filename matches exactly (case-sensitive)

**Frontend shows blank page or auth errors**
- Verify `frontend/.env` has the correct Firebase project values
- Open browser console for specific error messages

**Port already in use**
```bash
# Change ports in docker-compose.yml, e.g. "8001:8000" for backend
```

**Docker build fails**
```bash
docker-compose down
docker system prune -f
docker-compose up --build
```
