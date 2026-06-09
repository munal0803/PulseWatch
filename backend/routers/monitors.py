from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from firebase_client import db
from datetime import datetime, timezone

router = APIRouter()


class MonitorCreate(BaseModel):
    url: HttpUrl
    name: str = ""


def doc_to_monitor(doc):
    data = doc.to_dict()
    last_checked = data.get("lastCheckedAt")
    return {
        "id": doc.id,
        "url": data.get("url"),
        "name": data.get("name"),
        "lastStatus": data.get("lastStatus"),
        "lastResponseTime": data.get("lastResponseTime"),
        "lastCheckedAt": last_checked.isoformat() if last_checked else None,
    }


@router.post("/monitors", status_code=201)
def create_monitor(body: MonitorCreate):
    url_str = str(body.url)
    doc_ref = db.collection("monitors").document()
    now = datetime.now(timezone.utc)
    data = {
        "url": url_str,
        "name": body.name,
        "createdAt": now,
        "lastStatus": None,
        "lastResponseTime": None,
        "lastCheckedAt": None,
    }
    doc_ref.set(data)
    return {"id": doc_ref.id, **data, "createdAt": now.isoformat()}


@router.get("/monitors")
def list_monitors():
    docs = db.collection("monitors").stream()
    return [doc_to_monitor(doc) for doc in docs]


@router.get("/monitors/{monitor_id}/checks")
def get_checks(monitor_id: str):
    monitor_ref = db.collection("monitors").document(monitor_id)
    if not monitor_ref.get().exists:
        raise HTTPException(status_code=404, detail="Monitor not found")

    checks_ref = (
        monitor_ref.collection("checks")
        .order_by("checkedAt", direction="DESCENDING")
        .limit(20)
    )
    docs = checks_ref.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        checked_at = data.get("checkedAt")
        results.append(
            {
                "id": doc.id,
                "status": data.get("status"),
                "statusCode": data.get("statusCode"),
                "responseTimeMs": data.get("responseTimeMs"),
                "checkedAt": checked_at.isoformat() if checked_at else None,
            }
        )
    return results


@router.delete("/monitors/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: str):
    monitor_ref = db.collection("monitors").document(monitor_id)
    if not monitor_ref.get().exists:
        raise HTTPException(status_code=404, detail="Monitor not found")

    # Delete checks in batches of 100 to avoid streaming the entire subcollection
    # into memory and to handle monitors with thousands of historical checks.
    while True:
        checks = list(monitor_ref.collection("checks").limit(100).stream())
        if not checks:
            break
        batch = db.batch()
        for check in checks:
            batch.delete(check.reference)
        batch.commit()

    monitor_ref.delete()
