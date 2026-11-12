import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

from radar.pncp import (
    DEFAULT_READ_TIMEOUT,
    ELECTRONIC_AUCTION,
    MAX_PAGE_SIZE,
    PncpClient,
    PncpError,
    RateLimitedError,
)
from radar.profiling import field_coverage

RAW_DIR = Path("data/raw")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save one raw page of open tenders from PNCP.")
    parser.add_argument("--modality", type=int, default=ELECTRONIC_AUCTION)
    parser.add_argument(
        "--until",
        type=parse_date,
        default=date.today() + timedelta(days=30),
        help="Latest proposal deadline to include, as YYYY-MM-DD",
    )
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=MAX_PAGE_SIZE)
    parser.add_argument("--state", default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_READ_TIMEOUT)
    return parser.parse_args()


def output_path(args: argparse.Namespace) -> Path:
    state = args.state.upper() if args.state else "all"
    name = (
        f"open_tenders_m{args.modality}_{args.until:%Y%m%d}_{state}"
        f"_p{args.page}_s{args.page_size}.json"
    )
    return RAW_DIR / name


def print_summary(records: list[dict], total_records: int, total_pages: int) -> None:
    print(f"Records in this page: {len(records)}")
    print(f"Total records: {total_records}")
    print(f"Total pages: {total_pages}")
    if not records:
        return
    print("\nField coverage (filled / records):")
    for name, filled in field_coverage(records).items():
        print(f"  {name:<45} {filled}/{len(records)}")


def main() -> int:
    args = parse_args()
    print(f"Requesting page {args.page} (waiting up to {args.timeout:.0f}s)...")
    started = time.monotonic()
    try:
        with PncpClient(timeout=args.timeout) as client:
            page = client.fetch_open_tenders(
                modality_id=args.modality,
                closing_until=args.until,
                page=args.page,
                page_size=args.page_size,
                state_code=args.state,
            )
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1
    except RateLimitedError:
        print("[FAIL] Rate limited (HTTP 429). Wait a minute and try again.")
        return 1
    except PncpError as exc:
        print(f"[FAIL] {exc}")
        return 1
    except httpx.TimeoutException:
        elapsed = time.monotonic() - started
        print(f"[FAIL] No response after {elapsed:.0f}s. PNCP is slow or throttling; try again.")
        return 1
    except httpx.HTTPError as exc:
        print(f"[FAIL] Network error: {exc}")
        return 1

    elapsed = time.monotonic() - started
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = output_path(args)
    path.write_text(json.dumps(page.raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Saved {path} (response in {elapsed:.1f}s)\n")
    print_summary(page.records, page.total_records, page.total_pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
