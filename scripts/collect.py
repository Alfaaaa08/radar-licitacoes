import argparse
import sys
from datetime import date, timedelta

import psycopg

from radar.collector import BRAZILIAN_STATES, RetryPolicy, collect
from radar.db import connect
from radar.pncp import (
    DEFAULT_READ_TIMEOUT,
    ELECTRONIC_AUCTION,
    MAX_PAGE_SIZE,
    PncpClient,
    TenderPage,
)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_states(value: str) -> tuple[str, ...]:
    states = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    unknown = [state for state in states if state not in BRAZILIAN_STATES]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown state codes: {', '.join(unknown)}")
    return states


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect open tenders from PNCP into Postgres.")
    parser.add_argument("--modality", type=int, default=ELECTRONIC_AUCTION)
    parser.add_argument("--until", type=parse_date, default=date.today() + timedelta(days=30))
    parser.add_argument("--states", type=parse_states, default=BRAZILIAN_STATES)
    parser.add_argument("--page-size", type=int, default=MAX_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_READ_TIMEOUT)
    parser.add_argument("--attempts", type=int, default=RetryPolicy().max_attempts)
    return parser.parse_args()


def print_progress(state: str, page: TenderPage) -> None:
    print(
        f"{state}: page {page.page_number}/{page.total_pages} "
        f"({page.total_records} open tenders in {state})",
        flush=True,
    )


def main() -> int:
    args = parse_args()
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    try:
        with conn, PncpClient(timeout=args.timeout) as client:
            stats = collect(
                client,
                conn,
                modality_id=args.modality,
                closing_until=args.until,
                states=args.states,
                page_size=args.page_size,
                pause=args.pause,
                max_pages_per_state=args.max_pages,
                retry=RetryPolicy(max_attempts=args.attempts),
                on_page=print_progress,
            )
    except KeyboardInterrupt:
        print("\nInterrupted. The run was recorded in collection_runs.")
        return 130

    print(f"\nRun {stats.run_id} finished.")
    print(f"Pages fetched: {stats.pages}")
    print(f"Tenders seen: {stats.tenders_seen}")
    print(f"Tenders new: {stats.tenders_new}")
    print(f"Errors: {len(stats.errors)}")
    for error in stats.errors[:10]:
        print(f"  {error}")
    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
