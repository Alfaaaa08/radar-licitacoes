import sys

import psycopg

from radar.db import connect
from radar.migrations import apply_pending


def main() -> int:
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    with conn:
        applied = apply_pending(conn)

    if not applied:
        print("Nothing to apply. The database is up to date.")
        return 0
    for name in applied:
        print(f"[OK] Applied {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
