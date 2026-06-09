import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from routers.monitors import router as monitors_router
from scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitors_router, prefix="/api")

try:
    from google.api_core.exceptions import GoogleAPICallError

    @app.exception_handler(GoogleAPICallError)
    async def firestore_error_handler(request: Request, exc: GoogleAPICallError):
        logger.error(
            "Firestore error on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "Database service unavailable. Please try again later."},
        )

except ImportError:
    pass  # google-cloud-firestore not installed; skip handler


@app.get("/health")
def health():
    return {"status": "ok"}
