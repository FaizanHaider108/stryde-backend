import os
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials


def _get_or_init_firebase_app() -> firebase_admin.App:
    existing_apps = firebase_admin._apps  # type: ignore[attr-defined]
    if existing_apps:
        return firebase_admin.get_app()

    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
    if not service_account_path:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_PATH is not configured")

    cred_path = Path(service_account_path)
    if not cred_path.is_absolute():
        backend_root = Path(__file__).resolve().parents[2]
        cred_path = backend_root / cred_path

    if not cred_path.exists():
        raise RuntimeError(f"Firebase service account file not found: {cred_path}")

    cred = credentials.Certificate(str(cred_path))
    return firebase_admin.initialize_app(cred)


def verify_firebase_id_token(id_token: str) -> dict[str, Any]:
    _get_or_init_firebase_app()
    return auth.verify_id_token(id_token)
