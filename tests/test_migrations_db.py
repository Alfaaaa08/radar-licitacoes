from radar.migrations import MIGRATIONS_DIR, apply_pending


def test_migrations_are_idempotent(db_conn):
    assert apply_pending(db_conn) == []


def test_migrations_create_document_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
        tables = {row[0] for row in cur.fetchall()}

    assert {"tender_documents", "document_pages", "schema_migrations"} <= tables


def test_every_migration_is_recorded(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        recorded = [row[0] for row in cur.fetchall()]

    assert recorded == sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
