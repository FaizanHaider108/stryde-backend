"""
Prepare Postgres before uvicorn starts (Render / Docker).

Handles databases that already have tables but no Alembic history — the case that
causes: psycopg2.errors.DuplicateTable: relation "clubs" already exists

No manual Render Shell required: commit, push, redeploy.
"""
from __future__ import annotations

import os
import subprocess
import sys

# App tables that indicate schema was created outside Alembic (or history was lost).
_MARKER_TABLES = frozenset({"clubs", "users", "club_messages", "routes", "runs"})

_DUPLICATE_MARKERS = (
    "DuplicateTable",
    "already exists",
    "duplicate key",
    "relation ",
)


def _run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.check_call(args, cwd=os.environ.get("APP_ROOT", "/app"))


def _inspect_db() -> tuple[set[str], str | None]:
    """Return (public_table_names, alembic_revision_or_none)."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return set(), None

    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """
            )
        ).fetchall()
        tables = {str(r[0]) for r in rows}

        revision: str | None = None
        if "alembic_version" in tables:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            if row and row[0]:
                revision = str(row[0])

    return tables, revision


def _legacy_schema_without_revision(tables: set[str], revision: str | None) -> bool:
    if revision:
        return False
    return bool(_MARKER_TABLES & tables)


def _is_duplicate_schema_error(output: str) -> bool:
    lowered = output.lower()
    return any(m.lower() in lowered for m in _DUPLICATE_MARKERS)


def _upgrade_head() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=os.environ.get("APP_ROOT", "/app"),
    )


def main() -> int:
    if os.environ.get("SKIP_DB_MIGRATIONS", "").lower() in ("1", "true", "yes"):
        print("SKIP_DB_MIGRATIONS set — skipping Alembic.", flush=True)
        return 0

    print("Preparing database (Alembic)...", flush=True)

    try:
        tables, revision = _inspect_db()
    except Exception as exc:
        print(f"WARNING: Could not inspect database ({exc}). Running migrate anyway.", flush=True)
        tables, revision = set(), None

    if tables:
        print(f"Public tables found: {len(tables)} (alembic revision: {revision or 'none'})", flush=True)

    if _legacy_schema_without_revision(tables, revision):
        print(
            "Existing Stryde tables detected with no Alembic revision — "
            "stamping head before migrate.",
            flush=True,
        )
        _run("alembic", "stamp", "head")

    result = _upgrade_head()
    if result.returncode == 0:
        if result.stdout:
            print(result.stdout, end="", flush=True)
        print("Database migrations complete.", flush=True)
        return 0

    combined = f"{result.stdout}\n{result.stderr}"
    print(combined, end="", flush=True)

    if _is_duplicate_schema_error(combined):
        print(
            "Migrate hit existing tables — stamping Alembic to head, then applying pending migrations.",
            flush=True,
        )
        _run("alembic", "stamp", "head")
        retry = _upgrade_head()
        if retry.returncode == 0:
            if retry.stdout:
                print(retry.stdout, end="", flush=True)
            print("Database migrations complete after stamp.", flush=True)
            return 0
        print(retry.stdout, end="", flush=True)
        print(retry.stderr, end="", flush=True)
        return retry.returncode

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
