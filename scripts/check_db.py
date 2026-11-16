import sys

import psycopg

from radar.db import connect

EXPECTED_TABLES = {
    "tenders",
    "collection_runs",
    "tender_documents",
    "document_pages",
    "schema_migrations",
}


def main() -> int:
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        print("       Is the container running? Try: docker compose ps")
        return 1

    with conn, conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(f"[OK] Connected: {cur.fetchone()[0].split(',')[0]}")

        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
        if not row:
            print("[FAIL] pgvector extension not found.")
            return 1
        print(f"[OK] pgvector {row[0]}")

        cur.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
        print(f"[OK] Test vector distance: {cur.fetchone()[0]:.1f} (expected 1.0)")

        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = [r[0] for r in cur.fetchall()]
        missing = EXPECTED_TABLES - set(tables)
        if missing:
            print(f"[FAIL] Missing tables: {', '.join(sorted(missing))}")
            print("       Try: uv run python scripts/migrate.py")
            return 1
        print(f"[OK] Tables: {', '.join(tables)}")

    print("\nAll good. The database is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
