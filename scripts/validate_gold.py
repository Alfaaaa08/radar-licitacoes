import sys

import psycopg

from radar.db import connect
from radar.gold import ANNOTATIONS_DIR, SELECTION_PATH, read_selection, validate_annotation_file


def main() -> int:
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    files = sorted(ANNOTATIONS_DIR.glob("*.json"))
    problems = 0
    with conn:
        for path in files:
            issues = validate_annotation_file(conn, path)
            if issues:
                problems += 1
                print(f"[FAIL] {path.name}")
                for issue in issues:
                    print(f"       {issue}")
            else:
                print(f"[OK]   {path.name}")

    total = len(read_selection()) if SELECTION_PATH.exists() else 0
    print(f"\nAnnotations: {len(files)} of {total} selected tenders")
    print(f"With problems: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
