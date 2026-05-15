"""Run the FastAPI app with host/port from `backend/.env` (or defaults).

Usage (from the `backend` directory):

    python run_dev.py

Equivalent to:

    uvicorn app.main:app --host <UVICORN_HOST> --port <UVICORN_PORT>

Set `UVICORN_HOST` / `UVICORN_PORT` in `.env` (see `.env.example`). When you
change the port, set the app `EXPO_PUBLIC_API_BASE_URL` to the same host:port.

On Windows, binding to a concrete LAN IP (e.g. 192.168.x.x) can fail with
Errno 13; use host `0.0.0.0` here and keep your phone pointing at the LAN IP.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    port = int(os.getenv("UVICORN_PORT", "8000"))
    reload_flag = os.getenv("UVICORN_RELOAD", "true").lower() in ("1", "true", "yes")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_flag)


if __name__ == "__main__":
    main()
