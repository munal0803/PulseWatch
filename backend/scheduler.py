import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from firebase_client import db

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


async def ping_url(url: str) -> dict:
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    return {"status": "up", "statusCode": response.status_code, "responseTimeMs": elapsed_ms}


def ping_all_monitors():
    try:
        monitors = list(db.collection("monitors").stream())
    except Exception as exc:
        logger.error("Failed to fetch monitors from Firestore: %s", exc, exc_info=True)
        return

    if not monitors:
        return

    async def run_all():
        await asyncio.gather(
            *[ping_single(doc.id, doc.to_dict().get("url")) for doc in monitors]
        )

    async def ping_single(monitor_id: str, url: str):
        if not url:
            logger.warning("Monitor %s has no URL configured, skipping", monitor_id)
            return

        now = datetime.now(timezone.utc)
        try:
            result = await ping_url(url)
            status = result["status"]
            status_code = result["statusCode"]
            response_time = result["responseTimeMs"]
        except httpx.HTTPError as exc:
            logger.warning("HTTP error pinging %s: %s", url, exc)
            status = "down"
            status_code = None
            response_time = None
        except Exception as exc:
            logger.error("Unexpected error pinging %s: %s", url, exc, exc_info=True)
            status = "down"
            status_code = None
            response_time = None

        check_data = {
            "status": status,
            "statusCode": status_code,
            "responseTimeMs": response_time,
            "checkedAt": now,
        }

        try:
            monitor_ref = db.collection("monitors").document(monitor_id)
            monitor_ref.collection("checks").add(check_data)
            monitor_ref.update(
                {
                    "lastStatus": status,
                    "lastResponseTime": response_time,
                    "lastCheckedAt": now,
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to write check result for monitor %s: %s",
                monitor_id,
                exc,
                exc_info=True,
            )

    asyncio.run(run_all())


def start_scheduler():
    scheduler.add_job(
        ping_all_monitors,
        "interval",
        seconds=60,
        id="ping_monitors",
        replace_existing=True,
        max_instances=1,
    )
    if not scheduler.running:
        scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
