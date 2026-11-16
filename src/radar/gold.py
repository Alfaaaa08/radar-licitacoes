import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import psycopg
from pydantic import ValidationError

from radar.evidence import check_evidence
from radar.it_filter import normalize
from radar.schema import GoldAnnotation, TenderExtraction

GOLD_DIR = Path("gold")
ANNOTATIONS_DIR = GOLD_DIR / "annotations"
SELECTION_PATH = GOLD_DIR / "selection.json"

SPHERE_GROUPS = {"F": "federal", "E": "state", "D": "state", "M": "municipal"}
DEFAULT_QUOTAS = {"federal": 6, "state": 6, "municipal": 8}
GROUP_CYCLE = ("federal", "state", "municipal")
MAX_PER_STATE = 2

HINT_TERMS = {
    "proposal_deadline": [
        "recebimento das propostas",
        "envio das propostas",
        "propostas serao recebidas",
        "recebidas ate",
        "data limite",
        "encerramento",
        "abertura da sessao",
        "prazo para",
    ],
    "estimated_value": ["valor estimado", "valor total", "valor maximo", "orcamento", "sigilo"],
    "requires_technical_certificate": [
        "atestado",
        "capacidade tecnica",
        "qualificacao tecnica",
    ],
    "bid_bond_percentage": [
        "garantia de proposta",
        "garantia da proposta",
        "garantia de participacao",
    ],
    "performance_bond_percentage": [
        "garantia de execucao",
        "garantia contratual",
        "garantia de cumprimento",
    ],
    "site_visit": ["visita tecnica", "vistoria"],
    "small_business_preference": ["microempresa", "epp", "123/2006", "exclusiv", "cota reservada"],
}
MAX_HINTS_PER_FIELD = 8
MAX_HINT_LENGTH = 220

CANDIDATES_SQL = """
SELECT t.pncp_control_number, t.state_code, t.payload->'orgaoEntidade'->>'esferaId',
       t.object_description, d.document_sequence, d.page_count
FROM tenders t
JOIN LATERAL (
    SELECT document_sequence, page_count
    FROM tender_documents
    WHERE pncp_control_number = t.pncp_control_number
      AND text_status = 'text'
      AND page_count BETWEEN %(min_pages)s AND %(max_pages)s
    ORDER BY document_sequence
    LIMIT 1
) d ON TRUE
WHERE cardinality(t.it_matched_terms) > 0
ORDER BY md5(t.pncp_control_number || %(seed)s)
"""


@dataclass(frozen=True)
class Candidate:
    control_number: str
    state: str | None
    sphere: str
    object_description: str | None
    document_sequence: int
    page_count: int


@dataclass(frozen=True)
class Hint:
    page: int
    line: str


def fetch_candidates(
    conn: psycopg.Connection, seed: str = "1", min_pages: int = 3, max_pages: int = 300
) -> list[Candidate]:
    with conn.cursor() as cur:
        cur.execute(CANDIDATES_SQL, {"seed": seed, "min_pages": min_pages, "max_pages": max_pages})
        rows = cur.fetchall()
    conn.rollback()
    return [
        Candidate(number, state, SPHERE_GROUPS.get(sphere, "other"), description, doc, pages)
        for number, state, sphere, description, doc, pages in rows
    ]


def pick(
    pool: list[Candidate], wanted: int, chosen: list[Candidate], max_per_state: int | None
) -> None:
    taken = {candidate.control_number for candidate in chosen}
    for candidate in pool:
        if wanted <= 0:
            return
        if candidate.control_number in taken:
            continue
        in_state = sum(
            1
            for other in chosen
            if other.state == candidate.state and other.sphere == candidate.sphere
        )
        if max_per_state is not None and in_state >= max_per_state:
            continue
        chosen.append(candidate)
        taken.add(candidate.control_number)
        wanted -= 1


def interleave(chosen: list[Candidate]) -> list[Candidate]:
    queues = {group: [c for c in chosen if c.sphere == group] for group in (*GROUP_CYCLE, "other")}
    ordered = []
    while any(queues.values()):
        for group in (*GROUP_CYCLE, "other"):
            if queues[group]:
                ordered.append(queues[group].pop(0))
    return ordered


def select_candidates(
    candidates: list[Candidate],
    total: int = 20,
    quotas: dict[str, int] | None = None,
    max_per_state: int = MAX_PER_STATE,
) -> list[Candidate]:
    quotas = quotas or DEFAULT_QUOTAS
    by_group = {group: [c for c in candidates if c.sphere == group] for group in GROUP_CYCLE}
    chosen: list[Candidate] = []
    for group in GROUP_CYCLE:
        pick(by_group[group], quotas.get(group, 0), chosen, max_per_state)

    missing = total - len(chosen)
    if missing > 0:
        pick(candidates, missing, chosen, max_per_state)
        pick(candidates, total - len(chosen), chosen, None)
    return interleave(chosen[:total])


def write_selection(path: Path, selected: list[Candidate]) -> None:
    payload = [
        {"order": index, **asdict(candidate)} for index, candidate in enumerate(selected, start=1)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_selection(path: Path = SELECTION_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pages(conn: psycopg.Connection, control_number: str, document_sequence: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.text FROM document_pages p JOIN tender_documents d ON d.id = p.document_id "
            "WHERE d.pncp_control_number = %s AND d.document_sequence = %s "
            "ORDER BY p.page_number",
            (control_number, document_sequence),
        )
        pages = [row[0] for row in cur.fetchall()]
    conn.rollback()
    return pages


def find_hints(pages: list[str]) -> dict[str, list[Hint]]:
    found: dict[str, list[Hint]] = {field: [] for field in HINT_TERMS}
    for page_number, text in enumerate(pages, start=1):
        for line in text.splitlines():
            normalized = normalize(line)
            for field, terms in HINT_TERMS.items():
                if len(found[field]) >= MAX_HINTS_PER_FIELD:
                    continue
                if any(term in normalized for term in terms):
                    found[field].append(Hint(page_number, line.strip()[:MAX_HINT_LENGTH]))
    return found


def annotation_path(control_number: str, directory: Path = ANNOTATIONS_DIR) -> Path:
    return directory / f"{control_number.replace('/', '_')}.json"


def blank_annotation(
    control_number: str, document_sequence: int, annotator: str, today: date
) -> GoldAnnotation:
    return GoldAnnotation(
        control_number=control_number,
        document_sequence=document_sequence,
        annotator=annotator,
        annotated_on=today,
        extraction=TenderExtraction.blank(),
    )


def write_annotation(path: Path, annotation: GoldAnnotation) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = annotation.model_dump_json(indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def validate_annotation_file(conn: psycopg.Connection, path: Path) -> list[str]:
    try:
        annotation = GoldAnnotation.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        return [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
    except ValueError as exc:
        return [f"invalid JSON: {exc}"]

    pages = load_pages(conn, annotation.control_number, annotation.document_sequence)
    if not pages:
        return [
            f"no text stored for {annotation.control_number} document {annotation.document_sequence}"
        ]
    return [
        f"{issue.field}: {issue.message}" for issue in check_evidence(annotation.extraction, pages)
    ]
