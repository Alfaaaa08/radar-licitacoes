import zipfile

import pytest
from fakes import LONG_TEXT, FakeDocumentsClient, make_pdf_bytes

from radar.doc_pipeline import (
    DocumentStats,
    list_documents_for_tenders,
    process_pending_documents,
)
from radar.pncp import ServerError
from radar.retry import RetryPolicy

FAST_RETRY = RetryPolicy(max_attempts=2, base_delay=0.0)
CNPJ = "00000000000100"


def insert_tender(conn, sequence: int, terms: list[str], state: str = "SP"):
    control_number = f"{CNPJ}-1-{sequence:06d}/2026"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenders (pncp_control_number, agency_cnpj, purchase_year, "
            "purchase_sequence, state_code, payload, it_matched_terms, it_checked_at) "
            "VALUES (%s, %s, 2026, %s, %s, '{}', %s, now())",
            (control_number, CNPJ, sequence, state, terms),
        )
    conn.commit()
    return control_number


def edital(sequence: int, type_name: str = "Edital") -> dict:
    return {
        "sequencialDocumento": sequence,
        "tipoDocumentoId": 2,
        "tipoDocumentoNome": type_name,
        "titulo": f"Document {sequence}",
        "url": f"https://example.invalid/{sequence}",
        "dataPublicacaoPncp": "2026-11-01T10:00:00",
    }


def list_all(client, conn, stats=None, **kwargs):
    stats = stats or DocumentStats()
    list_documents_for_tenders(
        client, conn, stats, limit=100, pause=0.0, retry=FAST_RETRY, sleep=lambda s: None, **kwargs
    )
    return stats


def process_all(client, conn, tmp_path, stats=None):
    stats = stats or DocumentStats()
    process_pending_documents(
        client,
        conn,
        stats,
        limit=100,
        data_dir=tmp_path,
        pause=0.0,
        retry=FAST_RETRY,
        sleep=lambda s: None,
    )
    return stats


def document_rows(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT document_sequence, download_status, text_status, page_count "
            "FROM tender_documents ORDER BY document_sequence"
        )
        return cur.fetchall()


def test_only_it_tenders_are_listed_and_only_editais_are_pending(db_conn):
    insert_tender(db_conn, 1, ["software"])
    insert_tender(db_conn, 2, [])
    client = FakeDocumentsClient(
        {(CNPJ, 2026, 1): [edital(1), edital(2, "Termo de Referência"), edital(3, "Minuta")]}
    )

    stats = list_all(client, db_conn)

    assert client.list_calls == 1
    assert (stats.tenders_listed, stats.documents_found, stats.documents_wanted) == (1, 3, 1)
    assert document_rows(db_conn) == [
        (1, "pending", None, None),
        (2, "skipped", None, None),
        (3, "skipped", None, None),
    ]


def test_listing_is_not_repeated_for_already_listed_tenders(db_conn):
    insert_tender(db_conn, 1, ["software"])
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [edital(1)]})

    list_all(client, db_conn)
    list_all(client, db_conn)

    assert client.list_calls == 1
    assert len(document_rows(db_conn)) == 1


def test_inactive_documents_are_not_downloaded(db_conn):
    insert_tender(db_conn, 1, ["software"])
    inactive = {**edital(1), "statusAtivo": False}
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [inactive]})

    list_all(client, db_conn)

    assert document_rows(db_conn) == [(1, "skipped", None, None)]


def test_listing_failure_is_recorded_and_retried_next_run(db_conn):
    insert_tender(db_conn, 1, ["software"])
    insert_tender(db_conn, 2, ["software"])
    client = FakeDocumentsClient(
        {(CNPJ, 2026, 1): ServerError("500"), (CNPJ, 2026, 2): [edital(1)]}
    )

    stats = list_all(client, db_conn)

    assert stats.tenders_listed == 1
    assert stats.errors[0]["step"] == "list"
    client.listings[(CNPJ, 2026, 1)] = [edital(1)]
    list_all(client, db_conn)

    assert client.list_calls == 4
    assert len(document_rows(db_conn)) == 2


def test_text_pdf_is_downloaded_and_stored_page_by_page(db_conn, tmp_path):
    insert_tender(db_conn, 1, ["software"])
    pdf = make_pdf_bytes([f"First page. {LONG_TEXT}", f"Second page. {LONG_TEXT}"])
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [edital(1)]}, {1: [pdf]})
    list_all(client, db_conn)

    stats = process_all(client, db_conn, tmp_path)

    assert (stats.downloaded, stats.text, stats.scanned, stats.failed) == (1, 1, 0, 0)
    assert document_rows(db_conn) == [(1, "downloaded", "text", 2)]
    with db_conn.cursor() as cur:
        cur.execute("SELECT page_number, left(text, 10) FROM document_pages ORDER BY page_number")
        assert cur.fetchall() == [(1, "First page"), (2, "Second pag")]
        cur.execute("SELECT file_path, file_type, size_bytes, sha256 FROM tender_documents")
        file_path, file_type, size, sha = cur.fetchone()
    assert (tmp_path / file_path).read_bytes() == pdf
    assert (file_type, size, len(sha)) == ("pdf", len(pdf), 64)


def test_pdf_without_text_is_marked_scanned(db_conn, tmp_path):
    insert_tender(db_conn, 1, ["software"])
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [edital(1)]}, {1: [make_pdf_bytes(["", ""])]})
    list_all(client, db_conn)

    stats = process_all(client, db_conn, tmp_path)

    assert stats.scanned == 1
    assert document_rows(db_conn) == [(1, "downloaded", "scanned", 2)]


def test_non_pdf_file_is_unsupported(db_conn, tmp_path):
    insert_tender(db_conn, 1, ["software"])
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("a.txt", "hello")
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [edital(1)]}, {1: [archive.read_bytes()]})
    list_all(client, db_conn)

    stats = process_all(client, db_conn, tmp_path / "pdfs")

    assert stats.unsupported == 1
    assert document_rows(db_conn) == [(1, "downloaded", "unsupported", None)]


def test_corrupt_pdf_is_marked_failed_without_stopping_the_batch(db_conn, tmp_path):
    insert_tender(db_conn, 1, ["software"])
    good = make_pdf_bytes([LONG_TEXT])
    client = FakeDocumentsClient(
        {(CNPJ, 2026, 1): [edital(1), edital(2)]},
        {1: [b"%PDF-1.7 broken"], 2: [good]},
    )
    list_all(client, db_conn)

    stats = process_all(client, db_conn, tmp_path)

    assert (stats.failed, stats.text) == (1, 1)
    assert document_rows(db_conn) == [
        (1, "downloaded", "failed", None),
        (2, "downloaded", "text", 1),
    ]


def test_failed_download_is_retried_on_the_next_run(db_conn, tmp_path):
    insert_tender(db_conn, 1, ["software"])
    pdf = make_pdf_bytes([LONG_TEXT])
    client = FakeDocumentsClient(
        {(CNPJ, 2026, 1): [edital(1)]}, {1: [ServerError("500"), ServerError("500"), pdf]}
    )
    list_all(client, db_conn)

    first = process_all(client, db_conn, tmp_path)
    assert (first.failed, first.downloaded) == (1, 0)
    assert document_rows(db_conn) == [(1, "failed", None, None)]

    second = process_all(client, db_conn, tmp_path)
    assert (second.failed, second.downloaded, second.text) == (0, 1, 1)
    assert document_rows(db_conn) == [(1, "downloaded", "text", 1)]


def test_finished_documents_are_not_downloaded_again(db_conn, tmp_path):
    insert_tender(db_conn, 1, ["software"])
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [edital(1)]}, {1: [make_pdf_bytes([LONG_TEXT])]})
    list_all(client, db_conn)

    process_all(client, db_conn, tmp_path)
    process_all(client, db_conn, tmp_path)

    assert client.download_calls == [1]


def test_state_filter_limits_which_tenders_are_listed(db_conn):
    insert_tender(db_conn, 1, ["software"], state="SP")
    insert_tender(db_conn, 2, ["software"], state="MG")
    client = FakeDocumentsClient({(CNPJ, 2026, 1): [], (CNPJ, 2026, 2): []})

    list_all(client, db_conn, state="MG")

    assert client.list_calls == 1


@pytest.mark.parametrize("limit", [1])
def test_limit_caps_the_number_of_tenders_listed(db_conn, limit):
    for sequence in (1, 2, 3):
        insert_tender(db_conn, sequence, ["software"])
    client = FakeDocumentsClient({(CNPJ, 2026, n): [] for n in (1, 2, 3)})

    list_documents_for_tenders(
        client,
        db_conn,
        DocumentStats(),
        limit=limit,
        pause=0.0,
        retry=FAST_RETRY,
        sleep=lambda s: None,
    )

    assert client.list_calls == 1
