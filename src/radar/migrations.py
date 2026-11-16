from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "db" / "migrations"


def apply_pending(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT filename FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}
    conn.commit()

    newly_applied = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        conn.commit()
        newly_applied.append(path.name)
    return newly_applied
