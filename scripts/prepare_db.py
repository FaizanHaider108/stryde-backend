"""
Prepare Postgres before uvicorn (Render / Docker).

Fixes:
- DuplicateTable on deploy (schema exists, Alembic empty) → stamp base revision, upgrade
- Stamped at head but missing columns (e.g. users.apple_sub) → rewind Alembic, upgrade

Never stamps head while columns are missing — that caused signup 500 errors.
"""
from __future__ import annotations

import os
import subprocess
import sys

APP_ROOT = os.environ.get("APP_ROOT", "/app")

# First migration that creates core tables (clubs, users, …)
INITIAL_REVISION = "82709d7f2519"

# Oldest → newest: if column missing, rewind Alembic to `rewind_revision` then `upgrade head`
SCHEMA_REPAIRS: list[tuple[str, str, str]] = [
    ("users", "expo_push_token", "f3629094103d"),
    ("users", "notification_prefs", "add_expo_push_token"),
    ("users", "apple_sub", "add_attachments_to_club_messages"),
]

_DUPLICATE_MARKERS = (
    "duplicatetable",
    "already exists",
    "duplicate key",
)


def _run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.check_call(args, cwd=APP_ROOT)


def _engine():
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(url)


def _public_tables(conn) -> set[str]:
    from sqlalchemy import text

    rows = conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
    ).fetchall()
    return {str(r[0]) for r in rows}


def _has_column(conn, table: str, column: str) -> bool:
    from sqlalchemy import text

    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
              AND column_name = :column
            LIMIT 1
            """
        ),
        {"table": table, "column": column},
    ).fetchone()
    return row is not None


def _get_revision(conn) -> str | None:
    from sqlalchemy import text

    tables = _public_tables(conn)
    if "alembic_version" not in tables:
        return None
    row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])


def _set_revision(conn, revision: str) -> None:
    from sqlalchemy import text

    conn.execute(text("DELETE FROM alembic_version"))
    conn.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
        {"rev": revision},
    )
    conn.commit()


def _find_schema_rewind(conn) -> str | None:
    """Earliest Alembic revision to stamp so upgrade can add missing columns."""
    for table, column, rewind_revision in SCHEMA_REPAIRS:
        if table not in _public_tables(conn):
            continue
        if not _has_column(conn, table, column):
            return rewind_revision
    return None


def _repair_schema() -> bool:
    """Rewind Alembic if DB was stamped at head but migrations were skipped."""
    engine = _engine()
    with engine.connect() as conn:
        rewind = _find_schema_rewind(conn)
        if not rewind:
            return False
        current = _get_revision(conn)
        print(
            f"Schema repair: column(s) missing at Alembic revision {current!r} — "
            f"rewinding to {rewind!r}, then upgrading to head.",
            flush=True,
        )
        _set_revision(conn, rewind)
        return True


def _upgrade_head() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=APP_ROOT,
    )


def _is_duplicate_error(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _DUPLICATE_MARKERS)


def _handle_duplicate_migrate(output: str) -> int:
    """
    Tables already exist from an older schema — mark initial migration as done,
    then run remaining migrations (never stamp head).
    """
    print(
        "Migrate reported existing objects — stamping base revision "
        f"{INITIAL_REVISION}, then upgrading to head.",
        flush=True,
    )
    engine = _engine()
    with engine.connect() as conn:
        _set_revision(conn, INITIAL_REVISION)

    retry = _upgrade_head()
    if retry.returncode == 0:
        if retry.stdout:
            print(retry.stdout, end="", flush=True)
        print("Database migrations complete after base stamp.", flush=True)
        return 0

    print(retry.stdout, end="", flush=True)
    print(retry.stderr, end="", flush=True)
    return retry.returncode


def main() -> int:
    if os.environ.get("SKIP_DB_MIGRATIONS", "").lower() in ("1", "true", "yes"):
        print("SKIP_DB_MIGRATIONS set — skipping Alembic.", flush=True)
        return 0

    print("Preparing database (Alembic)...", flush=True)

    try:
        engine = _engine()
        with engine.connect() as conn:
            tables = _public_tables(conn)
            revision = _get_revision(conn)
        print(
            f"Public tables: {len(tables)} | Alembic revision: {revision or 'none'}",
            flush=True,
        )
    except Exception as exc:
        print(f"WARNING: DB inspect failed ({exc}). Continuing with migrate.", flush=True)

    # Fix incorrect `stamp head` from earlier deploys (missing apple_sub, etc.)
    try:
        _repair_schema()
    except Exception as exc:
        print(f"WARNING: Schema repair check failed ({exc}).", flush=True)

    result = _upgrade_head()
    if result.returncode == 0:
        if result.stdout:
            print(result.stdout, end="", flush=True)
        # Run repair again in case upgrade was no-op while still missing columns
        try:
            if _repair_schema():
                second = _upgrade_head()
                if second.returncode != 0:
                    combined = f"{second.stdout}\n{second.stderr}"
                    print(combined, end="", flush=True)
                    if _is_duplicate_error(combined):
                        return _handle_duplicate_migrate(combined)
                    return second.returncode
                if second.stdout:
                    print(second.stdout, end="", flush=True)
        except Exception as exc:
            print(f"WARNING: Post-upgrade schema repair failed ({exc}).", flush=True)

        print("Database migrations complete.", flush=True)
        return 0

    combined = f"{result.stdout}\n{result.stderr}"
    print(combined, end="", flush=True)

    if _is_duplicate_error(combined):
        return _handle_duplicate_migrate(combined)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
