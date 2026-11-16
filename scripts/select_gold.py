import argparse
import sys
from pathlib import Path

import psycopg

from radar.db import connect
from radar.gold import SELECTION_PATH, fetch_candidates, select_candidates, write_selection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pick the tenders that will be annotated by hand.")
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--seed", default="1")
    parser.add_argument("--output", type=Path, default=SELECTION_PATH)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.force:
        print(f"[FAIL] {args.output} already exists. Changing the gold set after annotating")
        print("       invalidates the measurements; use --force only before annotating.")
        return 1

    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    with conn:
        candidates = fetch_candidates(conn, seed=args.seed)

    print(f"Candidates (IT tenders with extracted text): {len(candidates)}")
    selected = select_candidates(candidates, total=args.total)
    if len(selected) < args.total:
        print(f"[FAIL] Only {len(selected)} suitable tenders. Collect and download more first.")
        return 1

    write_selection(args.output, selected)
    print(f"[OK] Wrote {args.output}\n")
    for index, candidate in enumerate(selected, start=1):
        description = (candidate.object_description or "")[:70]
        print(
            f"{index:>2}. {candidate.sphere:<9} {candidate.state or '--'} "
            f"{candidate.page_count:>3}p  {candidate.control_number}  {description}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
