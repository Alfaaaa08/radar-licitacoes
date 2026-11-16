import argparse
import sys
from datetime import date

from radar.gold import (
    ANNOTATIONS_DIR,
    SELECTION_PATH,
    annotation_path,
    blank_annotation,
    read_selection,
    write_annotation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a blank annotation file for a tender.")
    parser.add_argument("control_number", nargs="?")
    parser.add_argument("--next", action="store_true", help="Use the next tender without a file")
    parser.add_argument("--annotator", required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not SELECTION_PATH.exists():
        print(f"[FAIL] {SELECTION_PATH} not found. Run scripts/select_gold.py first.")
        return 1
    selection = read_selection()

    if args.next:
        pending = [
            item for item in selection if not annotation_path(item["control_number"]).exists()
        ]
        if not pending:
            print("Every selected tender already has an annotation file.")
            return 0
        item = pending[0]
    elif args.control_number:
        matches = [i for i in selection if i["control_number"] == args.control_number]
        if not matches:
            print(f"[FAIL] {args.control_number} is not in {SELECTION_PATH}.")
            return 1
        item = matches[0]
    else:
        print("[FAIL] Pass a control number or --next.")
        return 1

    path = annotation_path(item["control_number"], ANNOTATIONS_DIR)
    if path.exists() and not args.force:
        print(f"[FAIL] {path} already exists. Use --force to overwrite it.")
        return 1

    annotation = blank_annotation(
        item["control_number"], item["document_sequence"], args.annotator, date.today()
    )
    write_annotation(path, annotation)
    print(f"[OK] Created {path}")
    print(
        f"     Read it with: uv run python scripts/show_pages.py {item['control_number']} --hints"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
