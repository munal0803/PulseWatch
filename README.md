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

## Cloud Deployment

The backend deploys to **Google Cloud Run** and the frontend to **Firebase Hosting** — both integrate directly with the Firebase project already powering this app.

### Prerequisites

```bash
# Install Google Cloud CLI
brew install google-cloud-sdk          # macOS
# or visit https://cloud.google.com/sdk/docs/install for other platforms

# Install Firebase CLI
npm install -g firebase-tools

# Log in to both CLIs
gcloud auth login
firebase login

# Set your GCP project
gcloud config set project assignment-385ae
```

---

### Deploy the Backend — Google Cloud Run

Cloud Run runs the existing Docker container — no changes to the backend code needed.

**Step 1 — Store the service account key as a secret**

Never bake credentials into a Docker image. Use Google Cloud Secret Manager instead:

```bash
gcloud secrets create firebase-service-account-key \
  --data-file=serviceAccountKey.json
```

Grant Cloud Run permission to read the secret:

```bash
# Get your project number
PROJECT_NUMBER=$(gcloud projects describe assignment-385ae --format="value(projectNumber)")

gcloud secrets add-iam-policy-binding firebase-service-account-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**Step 2 — Build and push the backend image**

```bash
cd backend

gcloud builds submit \
  --tag gcr.io/assignment-385ae/pulsewatch-backend \
  --project assignment-385ae
```

**Step 3 — Deploy to Cloud Run**

```bash
gcloud run deploy pulsewatch-backend \
  --image gcr.io/assignment-385ae/pulsewatch-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --set-secrets="/app/serviceAccountKey.json=firebase-service-account-key:latest" \
  --set-env-vars="GOOGLE_APPLICATION_CREDENTIALS=/app/serviceAccountKey.json" \
  --project assignment-385ae
```

**Step 4 — Note the backend URL**

The command prints a Service URL like:
```
https://pulsewatch-backend-<hash>-uc.a.run.app
```

Copy it — you need it for the frontend.

---

### Deploy the Frontend — Firebase Hosting

**Step 1 — Update the backend API URL**

In `frontend/.env`, set the backend URL to the Cloud Run service URL from above:

```env
VITE_API_BASE_URL=https://pulsewatch-backend-<hash>-uc.a.run.app
```

**Step 2 — Build the frontend**

```bash
cd frontend
npm install
npm run build
# Output lands in frontend/dist/
```

**Step 3 — Initialise Firebase Hosting (first time only)**

```bash
cd frontend
firebase init hosting
```

When prompted:
- **Project:** select `assignment-385ae`
- **Public directory:** `dist`
- **Single-page app:** `Yes`
- **Overwrite dist/index.html:** `No`

This creates `frontend/firebase.json` and `.firebaserc`.

**Step 4 — Deploy**

```bash
firebase deploy --only hosting
```

Firebase prints the live URL:
```
Hosting URL: https://assignment-385ae.web.app
```

---

### Deployed URLs

| Service | URL |
|---------|-----|
| Frontend | https://assignment-385ae.web.app |
| Backend API | https://pulsewatch-backend-\<hash\>-uc.a.run.app |
| API Docs | https://pulsewatch-backend-\<hash\>-uc.a.run.app/docs |
| Health check | https://pulsewatch-backend-\<hash\>-uc.a.run.app/health |

---

### Redeploying After Changes

**Backend change:**
```bash
cd backend
gcloud builds submit --tag gcr.io/assignment-385ae/pulsewatch-backend
gcloud run deploy pulsewatch-backend --image gcr.io/assignment-385ae/pulsewatch-backend --region us-central1
```

**Frontend change:**
```bash
cd frontend
npm run build
firebase deploy --only hosting
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

**Cloud Run — permission denied on Firestore**
- Confirm the Secret Manager IAM binding was applied (see Deploy step 1)
- Check Cloud Run logs: `gcloud run logs read --service pulsewatch-backend --region us-central1`

**CORS errors after deploying frontend**
- Update `allow_origins` in `backend/main.py` to include your Firebase Hosting URL, then redeploy the backend
