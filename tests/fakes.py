from datetime import date

from radar.pncp import TenderPage

CLOSING_UNTIL = date(2026, 12, 11)


def make_record(number: int, state: str = "SP", **overrides) -> dict:
    record = {
        "numeroControlePNCP": f"00000000000100-1-{number:06d}/2026",
        "anoCompra": 2026,
        "sequencialCompra": number,
        "modalidadeId": 6,
        "objetoCompra": f"Object {number}",
        "valorTotalEstimado": 1000.5 + number,
        "dataPublicacaoPncp": "2026-11-01T10:00:00",
        "dataEncerramentoProposta": "2026-11-20T09:00:00",
        "orgaoEntidade": {"cnpj": "00000000000100", "razaoSocial": "Agency"},
        "unidadeOrgao": {"ufSigla": state},
    }
    record.update(overrides)
    return record


def make_page(records: list[dict], page_number: int, total_pages: int) -> TenderPage:
    return TenderPage(
        records=records,
        total_records=len(records) * total_pages,
        total_pages=total_pages,
        page_number=page_number,
        remaining_pages=total_pages - page_number,
        raw={},
    )


class ScriptedClient:
    def __init__(self, script: dict[str, list]):
        self.script = script
        self.calls: list[tuple[str | None, int]] = []

    def fetch_open_tenders(
        self, *, modality_id, closing_until, page=1, page_size=50, state_code=None
    ):
        self.calls.append((state_code, page))
        item = self.script[state_code][page - 1]
        if isinstance(item, BaseException):
            raise item
        return item


class FlakyClient:
    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch_open_tenders(self, **params):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
