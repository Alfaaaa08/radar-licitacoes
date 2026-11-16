import argparse
import sys

import psycopg

from radar.db import connect
from radar.gold import SELECTION_PATH, find_hints, load_pages, read_selection
from radar.it_filter import normalize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read the stored text of a tender notice.")
    parser.add_argument("control_number")
    parser.add_argument("--document", type=int, default=None)
    parser.add_argument("--page", type=int, default=None)
    parser.add_argument("--grep", default=None)
    parser.add_argument("--hints", action="store_true")
    return parser.parse_args()


def resolve_document(args: argparse.Namespace) -> int | None:
    if args.document:
        return args.document
    if SELECTION_PATH.exists():
        for item in read_selection():
            if item["control_number"] == args.control_number:
                return item["document_sequence"]
    return None


def main() -> int:
    args = parse_args()
    document = resolve_document(args)
    if document is None:
        print("[FAIL] Unknown document. Pass --document or select the tender first.")
        return 1

    try:
        conn = connect()
    except (psycopg.Error, RuntimeError) as exc:
        print(f"[FAIL] Could not connect to the database: {exc}")
        return 1

    with conn:
        pages = load_pages(conn, args.control_number, document)
    if not pages:
        print("[FAIL] No stored text for that tender and document.")
        return 1

    print(f"{args.control_number}  document {document}  {len(pages)} pages\n")

    if args.hints:
        for field, hints in find_hints(pages).items():
            print(f"== {field}")
            for hint in hints:
                print(f"  p.{hint.page:<3} {hint.line}")
        return 0

    if args.grep:
        needle = normalize(args.grep)
        for number, text in enumerate(pages, start=1):
            for line in text.splitlines():
                if needle in normalize(line):
                    print(f"p.{number:<3} {line.strip()}")
        return 0

    selected = [args.page] if args.page else range(1, len(pages) + 1)
    for number in selected:
        print(f"----- page {number} -----")
        print(pages[number - 1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
