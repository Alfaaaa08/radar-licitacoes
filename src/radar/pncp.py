from dataclasses import dataclass, field
from datetime import date
from typing import Self

import httpx

BASE_URL = "https://pncp.gov.br/api/consulta"
OPEN_PROPOSALS_PATH = "/v1/contratacoes/proposta"
ELECTRONIC_AUCTION = 6
MAX_PAGE_SIZE = 50
DEFAULT_READ_TIMEOUT = 60.0


class PncpError(Exception):
    pass


class RateLimitedError(PncpError):
    pass


class ServerError(PncpError):
    pass


@dataclass(frozen=True)
class TenderPage:
    records: list[dict]
    total_records: int
    total_pages: int
    page_number: int
    remaining_pages: int
    raw: dict = field(repr=False)


class PncpClient:
    def __init__(
        self, client: httpx.Client | None = None, timeout: float = DEFAULT_READ_TIMEOUT
    ) -> None:
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"Accept": "application/json"},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_open_tenders(
        self,
        *,
        modality_id: int,
        closing_until: date,
        page: int = 1,
        page_size: int = 50,
        state_code: str | None = None,
    ) -> TenderPage:
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}, got {page_size}")

        params: dict[str, str | int] = {
            "dataFinal": closing_until.strftime("%Y%m%d"),
            "codigoModalidadeContratacao": modality_id,
            "pagina": page,
            "tamanhoPagina": page_size,
        }
        if state_code:
            params["uf"] = state_code.upper()

        response = self._client.get(OPEN_PROPOSALS_PATH, params=params)

        if response.status_code == 204:
            return TenderPage([], 0, 0, page, 0, {})
        if response.status_code == 429:
            raise RateLimitedError("PNCP returned HTTP 429 (too many requests)")
        if response.status_code >= 500:
            raise ServerError(f"PNCP returned HTTP {response.status_code}: {response.text[:200]}")
        if response.is_error:
            raise PncpError(f"PNCP returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise PncpError("PNCP returned a response that is not valid JSON") from exc

        return TenderPage(
            records=payload.get("data", []),
            total_records=payload.get("totalRegistros", 0),
            total_pages=payload.get("totalPaginas", 0),
            page_number=payload.get("numeroPagina", page),
            remaining_pages=payload.get("paginasRestantes", 0),
            raw=payload,
        )
