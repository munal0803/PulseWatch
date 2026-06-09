import firebase_admin
from firebase_admin import credentials, firestore

try:
    cred = credentials.Certificate("./serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except FileNotFoundError:
    raise RuntimeError(
        "serviceAccountKey.json not found. "
        "Mount your Firebase service account key at ./serviceAccountKey.json"
    ) from None
except Exception as exc:
    raise RuntimeError(f"Firebase initialisation failed: {exc}") from exc
