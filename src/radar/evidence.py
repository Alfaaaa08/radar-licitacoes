import re
from dataclasses import dataclass

from radar.it_filter import normalize
from radar.schema import FIELD_NAMES, TenderExtraction


@dataclass(frozen=True)
class EvidenceIssue:
    field: str
    message: str


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", normalize(text)).strip()


def check_evidence(extraction: TenderExtraction, pages: list[str]) -> list[EvidenceIssue]:
    issues = []
    for name in FIELD_NAMES:
        evidence = getattr(extraction, name).evidence
        if evidence is None:
            continue
        if evidence.page > len(pages):
            issues.append(
                EvidenceIssue(
                    name, f"page {evidence.page} does not exist (document has {len(pages)})"
                )
            )
            continue
        if normalize_for_match(evidence.quote) not in normalize_for_match(pages[evidence.page - 1]):
            issues.append(EvidenceIssue(name, f"quote not found on page {evidence.page}"))
    return issues
