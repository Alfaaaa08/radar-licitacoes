import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import psycopg
from psycopg.types.json import Jsonb

from radar.collector import parse_timestamp
from radar.documents import PncpDocumentsClient
from radar.it_filter import normalize
from radar.pdf_text import PdfError, extract_text
from radar.pncp import PncpError
from radar.retry import DEFAULT_RETRY, RetryPolicy, retry_call

FETCH_ERRORS = (PncpError, httpx.TransportError)
DEFAULT_WANTED_TYPES = ("edital",)

SELECT_TENDERS_TO_LIST = """
SELECT pncp_control_number, agency_cnpj, purchase_year, purchase_sequence
FROM tenders
WHERE cardinality(it_matched_terms) > 0
  AND documents_listed_at IS NULL
  AND (%(state)s::text IS NULL OR state_code = %(state)s)
ORDER BY proposals_close_at DESC NULLS LAST, pncp_control_number
LIMIT %(limit)s
"""

UPSERT_DOCUMENT_SQL = """
INSERT INTO tender_documents (
    pncp_control_number, document_sequence, document_type_id, document_type_name,
    title, source_url, published_at, payload, download_status
) VALUES (
    %(pncp_control_number)s, %(document_sequence)s, %(document_type_id)s,
    %(document_type_name)s, %(title)s, %(source_url)s, %(published_at)s, %(payload)s,
    %(download_status)s
)
ON CONFLICT (pncp_control_number, document_sequence) DO UPDATE SET
    document_type_id = EXCLUDED.document_type_id,
    document_type_name = EXCLUDED.document_type_name,
    title = EXCLUDED.title,
    source_url = EXCLUDED.source_url,
    published_at = EXCLUDED.published_at,
    payload = EXCLUDED.payload
"""

SELECT_PENDING_DOCUMENTS = """
SELECT d.id, d.pncp_control_number, d.document_sequence, d.file_path,
       t.agency_cnpj, t.purchase_year, t.purchase_sequence
FROM tender_documents d
JOIN tenders t USING (pncp_control_number)
WHERE d.download_status IN ('pending', 'failed')
   OR (d.download_status = 'downloaded' AND d.text_status IS NULL)
ORDER BY d.id
LIMIT %(limit)s
"""


@dataclass
class DocumentStats:
    tenders_listed: int = 0
    documents_found: int = 0
    documents_wanted: int = 0
    downloaded: int = 0
    text: int = 0
    scanned: int = 0
    unsupported: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)


def is_wanted_type(type_name: str | None, wanted_types: tuple[str, ...]) -> bool:
    if not type_name:
        return False
    normalized = normalize(type_name)
    return any(wanted in normalized for wanted in wanted_types)


def is_active(document: dict) -> bool:
    for key in ("statusAtivo", "ativo"):
        if document.get(key) is False:
            return False
    return True


def document_row(control_number: str, document: dict, wanted_types: tuple[str, ...]) -> dict | None:
    sequence = document.get("sequencialDocumento")
    if sequence is None:
        return None
    wanted = is_active(document) and is_wanted_type(document.get("tipoDocumentoNome"), wanted_types)
    return {
        "pncp_control_number": control_number,
        "document_sequence": sequence,
        "document_type_id": document.get("tipoDocumentoId"),
        "document_type_name": document.get("tipoDocumentoNome"),
        "title": document.get("titulo"),
        "source_url": document.get("url"),
        "published_at": parse_timestamp(document.get("dataPublicacaoPncp")),
        "payload": Jsonb(document),
        "download_status": "pending" if wanted else "skipped",
    }


def list_documents_for_tenders(
    client: PncpDocumentsClient,
    conn: psycopg.Connection,
    stats: DocumentStats,
    *,
    limit: int,
    state: str | None = None,
    wanted_types: tuple[str, ...] = DEFAULT_WANTED_TYPES,
    pause: float = 1.0,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    with conn.cursor() as cur:
        cur.execute(SELECT_TENDERS_TO_LIST, {"state": state, "limit": limit})
        tenders = cur.fetchall()
    conn.rollback()

    for control_number, cnpj, year, sequence in tenders:
        try:
            documents = retry_call(
                lambda c=cnpj, y=year, s=sequence: client.list_documents(c, y, s), retry, sleep
            )
        except FETCH_ERRORS as exc:
            stats.errors.append({"tender": control_number, "step": "list", "error": str(exc)})
            continue

        rows = [
            row for doc in documents if (row := document_row(control_number, doc, wanted_types))
        ]
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(UPSERT_DOCUMENT_SQL, row)
            cur.execute(
                "UPDATE tenders SET documents_listed_at = now() WHERE pncp_control_number = %s",
                (control_number,),
            )
        conn.commit()

        stats.tenders_listed += 1
        stats.documents_found += len(rows)
        stats.documents_wanted += sum(1 for row in rows if row["download_status"] == "pending")
        sleep(pause)


def relative_path(
    cnpj: str, year: int, sequence: int, document_sequence: int, file_type: str
) -> str:
    extension = {"pdf": "pdf", "zip": "zip"}.get(file_type, "bin")
    return f"{cnpj}-{year}-{sequence}-{document_sequence}.{extension}"


def store_pages(conn: psycopg.Connection, document_id: int, pages: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_pages WHERE document_id = %s", (document_id,))
        cur.executemany(
            "INSERT INTO document_pages (document_id, page_number, text) VALUES (%s, %s, %s)",
            [(document_id, number, text) for number, text in enumerate(pages, start=1)],
        )


def mark_failed(conn: psycopg.Connection, document_id: int, message: str) -> None:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tender_documents SET download_status = 'failed', download_error = %s "
            "WHERE id = %s",
            (message, document_id),
        )
    conn.commit()


def process_document(
    client: PncpDocumentsClient,
    conn: psycopg.Connection,
    stats: DocumentStats,
    row: tuple,
    data_dir: Path,
    retry: RetryPolicy,
    sleep: Callable[[float], None],
) -> None:
    document_id, control_number, document_sequence, file_path, cnpj, year, sequence = row

    path = data_dir / file_path if file_path and (data_dir / file_path).exists() else None
    file_type = None
    if path is None:
        temporary = data_dir / f"{cnpj}-{year}-{sequence}-{document_sequence}.download"
        try:
            downloaded = retry_call(
                lambda: client.download_document(
                    cnpj, year, sequence, document_sequence, temporary
                ),
                retry,
                sleep,
            )
        except FETCH_ERRORS as exc:
            stats.failed += 1
            stats.errors.append(
                {"tender": control_number, "document": document_sequence, "error": str(exc)}
            )
            mark_failed(conn, document_id, str(exc))
            return

        file_type = downloaded.file_type
        file_path = relative_path(cnpj, year, sequence, document_sequence, file_type)
        path = data_dir / file_path
        temporary.replace(path)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tender_documents SET download_status = 'downloaded', download_error = NULL, "
                "file_path = %s, file_type = %s, size_bytes = %s, sha256 = %s, "
                "downloaded_at = now() WHERE id = %s",
                (file_path, file_type, downloaded.size_bytes, downloaded.sha256, document_id),
            )
        conn.commit()
        stats.downloaded += 1
    else:
        file_type = "pdf" if path.suffix == ".pdf" else "other"

    if file_type != "pdf":
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tender_documents SET text_status = 'unsupported' WHERE id = %s",
                (document_id,),
            )
        conn.commit()
        stats.unsupported += 1
        return

    try:
        extracted = extract_text(path)
    except PdfError as exc:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tender_documents SET text_status = 'failed', download_error = %s "
                "WHERE id = %s",
                (str(exc), document_id),
            )
        conn.commit()
        stats.failed += 1
        stats.errors.append(
            {"tender": control_number, "document": document_sequence, "error": str(exc)}
        )
        return

    store_pages(conn, document_id, extracted.pages)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tender_documents SET text_status = %s, page_count = %s, char_count = %s "
            "WHERE id = %s",
            (extracted.status, len(extracted.pages), extracted.char_count, document_id),
        )
    conn.commit()
    if extracted.status == "scanned":
        stats.scanned += 1
    else:
        stats.text += 1


def process_pending_documents(
    client: PncpDocumentsClient,
    conn: psycopg.Connection,
    stats: DocumentStats,
    *,
    limit: int,
    data_dir: Path,
    pause: float = 1.0,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    with conn.cursor() as cur:
        cur.execute(SELECT_PENDING_DOCUMENTS, {"limit": limit})
        rows = cur.fetchall()
    conn.rollback()

    data_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        process_document(client, conn, stats, row, data_dir, retry, sleep)
        sleep(pause)
