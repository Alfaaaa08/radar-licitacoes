import argparse
import sys
from collections import Counter

import psycopg

from radar.db import connect
from radar.it_filter import find_it_terms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tag tenders whose object mentions IT terms.")
    parser.add_argument("--recompute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    with conn:
        with conn.cursor() as cur:
            condition = "" if args.recompute else "WHERE it_checked_at IS NULL"
            cur.execute(f"SELECT pncp_control_number, object_description FROM tenders {condition}")
            tenders = cur.fetchall()

        updates = [(find_it_terms(description), number) for number, description in tenders]
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE tenders SET it_matched_terms = %s, it_checked_at = now() "
                "WHERE pncp_control_number = %s",
                updates,
            )
        conn.commit()

    matched = [terms for terms, _ in updates if terms]
    print(f"Tenders checked: {len(updates)}")
    print(f"Tenders matching at least one IT term: {len(matched)}")
    if updates:
        print(f"Match rate: {len(matched) / len(updates):.1%}")
    counts = Counter(term for terms in matched for term in terms)
    print("\nMost common terms:")
    for term, count in counts.most_common(15):
        print(f"  {term:<28} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
