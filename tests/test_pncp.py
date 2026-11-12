from datetime import date

import httpx
import pytest

from radar.pncp import BASE_URL, PncpClient, PncpError, RateLimitedError


def make_client(handler) -> PncpClient:
    transport = httpx.MockTransport(handler)
    return PncpClient(httpx.Client(transport=transport, base_url=BASE_URL))


def test_fetch_open_tenders_sends_expected_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": []})

    make_client(handler).fetch_open_tenders(
        modality_id=6,
        closing_until=date(2026, 12, 31),
        page=2,
        page_size=20,
        state_code="sp",
    )

    assert seen == {
        "path": "/api/consulta/v1/contratacoes/proposta",
        "dataFinal": "20261231",
        "codigoModalidadeContratacao": "6",
        "pagina": "2",
        "tamanhoPagina": "20",
        "uf": "SP",
    }


def test_fetch_open_tenders_omits_state_when_not_given():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"data": []})

    make_client(handler).fetch_open_tenders(modality_id=6, closing_until=date(2026, 12, 31))

    assert "uf" not in seen


def test_fetch_open_tenders_parses_page():
    payload = {
        "data": [{"numeroControlePNCP": "1-1-1/2026"}],
        "totalRegistros": 41,
        "totalPaginas": 5,
        "numeroPagina": 1,
        "paginasRestantes": 4,
        "empty": False,
    }
    client = make_client(lambda request: httpx.Response(200, json=payload))

    page = client.fetch_open_tenders(modality_id=6, closing_until=date(2026, 12, 31))

    assert page.records == payload["data"]
    assert page.total_records == 41
    assert page.total_pages == 5
    assert page.remaining_pages == 4
    assert page.raw == payload


def test_no_content_means_empty_page():
    client = make_client(lambda request: httpx.Response(204))

    page = client.fetch_open_tenders(modality_id=6, closing_until=date(2026, 12, 31))

    assert page.records == []
    assert page.total_records == 0


def test_rate_limit_raises_specific_error():
    client = make_client(lambda request: httpx.Response(429, text="<html>slow down</html>"))

    with pytest.raises(RateLimitedError):
        client.fetch_open_tenders(modality_id=6, closing_until=date(2026, 12, 31))


def test_server_error_raises_pncp_error():
    client = make_client(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(PncpError):
        client.fetch_open_tenders(modality_id=6, closing_until=date(2026, 12, 31))


@pytest.mark.parametrize("page_size", [0, 51, 500])
def test_page_size_outside_accepted_range_is_rejected_before_any_request(page_size):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be sent")

    client = make_client(handler)

    with pytest.raises(ValueError, match="page_size"):
        client.fetch_open_tenders(
            modality_id=6, closing_until=date(2026, 12, 31), page_size=page_size
        )


def test_non_json_body_raises_pncp_error():
    client = make_client(lambda request: httpx.Response(200, text="<html></html>"))

    with pytest.raises(PncpError):
        client.fetch_open_tenders(modality_id=6, closing_until=date(2026, 12, 31))
