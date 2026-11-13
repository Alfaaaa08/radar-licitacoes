import uuid
from pathlib import Path

import psycopg
import pytest

from radar.db import connect

INIT_SQL = Path(__file__).parent.parent / "db" / "init.sql"


@pytest.fixture
def db_conn():
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError):
        pytest.skip("database not available")

    schema = f"test_{uuid.uuid4().hex[:10]}"
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema}")
        cur.execute(f"SET search_path TO {schema}, public")
        cur.execute(INIT_SQL.read_text(encoding="utf-8"))
    conn.commit()

    yield conn

    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.commit()
    conn.close()
