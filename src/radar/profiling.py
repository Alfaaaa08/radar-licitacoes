from collections import Counter


def flatten(record: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in record.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def is_filled(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def field_coverage(records: list[dict]) -> dict[str, int]:
    names: set[str] = set()
    filled: Counter[str] = Counter()
    for record in records:
        flat = flatten(record)
        names.update(flat)
        filled.update(name for name, value in flat.items() if is_filled(value))
    return {name: filled[name] for name in sorted(names)}
