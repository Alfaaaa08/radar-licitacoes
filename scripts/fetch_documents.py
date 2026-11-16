import argparse
import sys
from pathlib import Path

import psycopg

from radar.db import connect
from radar.doc_pipeline import (
    DEFAULT_WANTED_TYPES,
    DocumentStats,
    list_documents_for_tenders,
    process_pending_documents,
)
from radar.documents import PncpDocumentsClient
from radar.pncp import DEFAULT_READ_TIMEOUT
from radar.retry import RetryPolicy

SUMMARY_SQL = """
SELECT COALESCE(text_status, download_status) AS status, count(*)
FROM tender_documents
GROUP BY 1
ORDER BY 2 DESC
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List, download and extract text from the documents of IT-related tenders."
    )
    parser.add_argument("--limit-tenders", type=int, default=50)
    parser.add_argument("--limit-documents", type=int, default=200)
    parser.add_argument("--state", default=None)
    parser.add_argument("--types", default=",".join(DEFAULT_WANTED_TYPES))
    parser.add_argument("--data-dir", type=Path, default=Path("data/pdfs"))
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_READ_TIMEOUT)
    parser.add_argument("--attempts", type=int, default=RetryPolicy().max_attempts)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    wanted = tuple(part.strip().lower() for part in args.types.split(",") if part.strip())
    retry = RetryPolicy(max_attempts=args.attempts)
    stats = DocumentStats()

    try:
        with conn, PncpDocumentsClient(timeout=args.timeout) as client:
            list_documents_for_tenders(
                client,
                conn,
                stats,
                limit=args.limit_tenders,
                state=args.state.upper() if args.state else None,
                wanted_types=wanted,
                pause=args.pause,
                retry=retry,
            )
            print(
                f"Listed {stats.tenders_listed} tenders: {stats.documents_found} documents, "
                f"{stats.documents_wanted} to download",
                flush=True,
            )
            process_pending_documents(
                client,
                conn,
                stats,
                limit=args.limit_documents,
                data_dir=args.data_dir,
                pause=args.pause,
                retry=retry,
            )
            with conn.cursor() as cur:
                cur.execute(SUMMARY_SQL)
                summary = cur.fetchall()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress is saved; run again to continue.")
        return 130

    print(f"Downloaded: {stats.downloaded}")
    print(f"With text: {stats.text}")
    print(f"Scanned (no text layer): {stats.scanned}")
    print(f"Unsupported file type: {stats.unsupported}")
    print(f"Failed: {stats.failed}")
    print("\nAll documents in the database, by status:")
    for status, count in summary:
        print(f"  {status:<12} {count}")
    for error in stats.errors[:10]:
        print(f"  {error}")
    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
