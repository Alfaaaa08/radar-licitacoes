import hashlib

import httpx
import pytest

from radar.documents import (
    DOCUMENTS_BASE_URL,
    MAX_DOWNLOAD_BYTES,
    PncpDocumentsClient,
    detect_file_type,
)
from radar.pncp import NotFoundError, PncpError, RateLimitedError, ServerError


def make_client(handler) -> PncpDocumentsClient:
    transport = httpx.MockTransport(handler)
    return PncpDocumentsClient(
        httpx.Client(transport=transport, base_url=DOCUMENTS_BASE_URL, follow_redirects=True)
    )


def test_list_documents_accepts_a_plain_list():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"sequencialDocumento": 1}])

    documents = make_client(handler).list_documents("123", 2026, 7)

    assert seen["path"] == "/pncp-api/v1/orgaos/123/compras/2026/7/arquivos"
    assert documents == [{"sequencialDocumento": 1}]


def test_list_documents_accepts_the_documentos_envelope():
    client = make_client(lambda r: httpx.Response(200, json={"documentos": [{"a": 1}]}))

    assert client.list_documents("123", 2026, 7) == [{"a": 1}]


@pytest.mark.parametrize("status", [204, 404])
def test_list_documents_treats_no_content_and_not_found_as_empty(status):
    client = make_client(lambda r: httpx.Response(status))

    assert client.list_documents("123", 2026, 7) == []


def test_list_documents_raises_typed_errors():
    with pytest.raises(RateLimitedError):
        make_client(lambda r: httpx.Response(429)).list_documents("1", 2026, 1)
    with pytest.raises(ServerError):
        make_client(lambda r: httpx.Response(500, text="boom")).list_documents("1", 2026, 1)


def test_list_documents_rejects_unexpected_shapes():
    client = make_client(lambda r: httpx.Response(200, json="nope"))

    with pytest.raises(PncpError):
        client.list_documents("1", 2026, 1)


def test_download_writes_file_and_reports_hash_and_type(tmp_path):
    content = b"%PDF-1.7 fake pdf bytes"
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, content=content)

    target = tmp_path / "nested" / "doc.pdf"

    result = make_client(handler).download_document("123", 2026, 7, 3, target)

    assert seen["path"] == "/pncp-api/v1/orgaos/123/compras/2026/7/arquivos/3"
    assert target.read_bytes() == content
    assert result.size_bytes == len(content)
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.file_type == "pdf"
    assert not list(tmp_path.rglob("*.part"))


def test_download_follows_redirects(tmp_path):
    def handler(request):
        if request.url.path.endswith("/arquivos/1"):
            return httpx.Response(302, headers={"Location": "/pncp-api/files/abc"})
        return httpx.Response(200, content=b"%PDF-redirected")

    target = tmp_path / "doc.pdf"

    make_client(handler).download_document("1", 2026, 1, 1, target)

    assert target.read_bytes() == b"%PDF-redirected"


def test_failed_download_leaves_no_partial_file(tmp_path):
    target = tmp_path / "doc.pdf"

    with pytest.raises(ServerError):
        make_client(lambda r: httpx.Response(500, text="boom")).download_document(
            "1", 2026, 1, 1, target
        )

    assert not target.exists()
    assert not list(tmp_path.glob("*.part"))


def test_empty_download_is_an_error(tmp_path):
    with pytest.raises(NotFoundError):
        make_client(lambda r: httpx.Response(200, content=b"")).download_document(
            "1", 2026, 1, 1, tmp_path / "doc.pdf"
        )


def test_oversized_download_is_aborted(tmp_path, monkeypatch):
    monkeypatch.setattr("radar.documents.MAX_DOWNLOAD_BYTES", 10)
    target = tmp_path / "doc.pdf"

    with pytest.raises(PncpError, match="larger"):
        make_client(lambda r: httpx.Response(200, content=b"x" * 100)).download_document(
            "1", 2026, 1, 1, target
        )

    assert not target.exists()
    assert MAX_DOWNLOAD_BYTES > 10


@pytest.mark.parametrize(
    ("head", "expected"),
    [(b"%PDF-1.4", "pdf"), (b"PK\x03\x04", "zip"), (b"<html>", "other"), (b"", "other")],
)
def test_detect_file_type(head, expected):
    assert detect_file_type(head) == expected
