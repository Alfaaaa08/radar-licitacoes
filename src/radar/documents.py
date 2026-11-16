import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import httpx

from radar.pncp import (
    DEFAULT_READ_TIMEOUT,
    NotFoundError,
    PncpError,
    raise_for_status,
)

DOCUMENTS_BASE_URL = "https://pncp.gov.br/pncp-api"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class DownloadedFile:
    size_bytes: int
    sha256: str
    file_type: str


def detect_file_type(head: bytes) -> str:
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        return "zip"
    return "other"


class PncpDocumentsClient:
    def __init__(
        self, client: httpx.Client | None = None, timeout: float = DEFAULT_READ_TIMEOUT
    ) -> None:
        self._client = client or httpx.Client(
            base_url=DOCUMENTS_BASE_URL,
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def list_documents(self, cnpj: str, year: int, sequence: int) -> list[dict]:
        response = self._client.get(
            f"/v1/orgaos/{cnpj}/compras/{year}/{sequence}/arquivos",
            headers={"Accept": "application/json"},
        )
        if response.status_code in (204, 404):
            return []
        raise_for_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise PncpError("PNCP returned a document list that is not valid JSON") from exc
        if isinstance(payload, dict):
            payload = payload.get("documentos", [])
        if not isinstance(payload, list):
            raise PncpError("PNCP returned a document list in an unexpected shape")
        return payload

    def download_document(
        self, cnpj: str, year: int, sequence: int, document_sequence: int, destination: Path
    ) -> DownloadedFile:
        url = f"/v1/orgaos/{cnpj}/compras/{year}/{sequence}/arquivos/{document_sequence}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        digest = hashlib.sha256()
        size = 0
        head = b""

        try:
            with self._client.stream("GET", url, headers={"Accept": "*/*"}) as response:
                if response.is_error:
                    response.read()
                    raise_for_status(response)
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        if not head:
                            head = chunk[:8]
                        size += len(chunk)
                        if size > MAX_DOWNLOAD_BYTES:
                            raise PncpError(f"document is larger than {MAX_DOWNLOAD_BYTES} bytes")
                        digest.update(chunk)
                        handle.write(chunk)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

        if size == 0:
            partial.unlink(missing_ok=True)
            raise NotFoundError("PNCP returned an empty document")

        partial.replace(destination)
        return DownloadedFile(
            size_bytes=size, sha256=digest.hexdigest(), file_type=detect_file_type(head)
        )
