import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx
import psycopg
from psycopg.types.json import Jsonb

from radar.pncp import (
    MAX_PAGE_SIZE,
    PncpClient,
    PncpError,
    RateLimitedError,
    ServerError,
    TenderPage,
)

BRAZILIAN_STATES = (
    "AC",
    "AL",
    "AM",
    "AP",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MG",
    "MS",
    "MT",
    "PA",
    "PB",
    "PE",
    "PI",
    "PR",
    "RJ",
    "RN",
    "RO",
    "RR",
    "RS",
    "SC",
    "SE",
    "SP",
    "TO",
)

BRASILIA_OFFSET = timezone(timedelta(hours=-3))

RETRYABLE_ERRORS = (RateLimitedError, ServerError, httpx.TransportError)
FETCH_ERRORS = (PncpError, httpx.TransportError)

UPSERT_SQL = """
INSERT INTO tenders (
    pncp_control_number, agency_cnpj, purchase_year, purchase_sequence, modality_id,
    state_code, object_description, estimated_value, published_at, proposals_close_at, payload
) VALUES (
    %(pncp_control_number)s, %(agency_cnpj)s, %(purchase_year)s, %(purchase_sequence)s,
    %(modality_id)s, %(state_code)s, %(object_description)s, %(estimated_value)s,
    %(published_at)s, %(proposals_close_at)s, %(payload)s
)
ON CONFLICT (pncp_control_number) DO UPDATE SET
    agency_cnpj = EXCLUDED.agency_cnpj,
    purchase_year = EXCLUDED.purchase_year,
    purchase_sequence = EXCLUDED.purchase_sequence,
    modality_id = EXCLUDED.modality_id,
    state_code = EXCLUDED.state_code,
    object_description = EXCLUDED.object_description,
    estimated_value = EXCLUDED.estimated_value,
    published_at = EXCLUDED.published_at,
    proposals_close_at = EXCLUDED.proposals_close_at,
    payload = EXCLUDED.payload,
    updated_at = now()
WHERE tenders.payload IS DISTINCT FROM EXCLUDED.payload
RETURNING (xmax = 0) AS inserted
"""


class MalformedRecordError(Exception):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 2.0
    max_delay: float = 60.0

    def delay(self, attempt: int) -> float:
        return min(self.max_delay, self.base_delay * 2**attempt)


DEFAULT_RETRY = RetryPolicy()


@dataclass
class RunStats:
    run_id: int
    pages: int = 0
    tenders_seen: int = 0
    tenders_new: int = 0
    errors: list[dict] = field(default_factory=list)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=BRASILIA_OFFSET)


def parse_tender(record: dict) -> dict:
    agency = record.get("orgaoEntidade") or {}
    unit = record.get("unidadeOrgao") or {}
    required = {
        "numeroControlePNCP": record.get("numeroControlePNCP"),
        "orgaoEntidade.cnpj": agency.get("cnpj"),
        "anoCompra": record.get("anoCompra"),
        "sequencialCompra": record.get("sequencialCompra"),
    }
    missing = [name for name, value in required.items() if value in (None, "")]
    if missing:
        raise MalformedRecordError(f"missing required fields: {', '.join(missing)}")

    return {
        "pncp_control_number": record["numeroControlePNCP"],
        "agency_cnpj": agency["cnpj"],
        "purchase_year": record["anoCompra"],
        "purchase_sequence": record["sequencialCompra"],
        "modality_id": record.get("modalidadeId"),
        "state_code": unit.get("ufSigla"),
        "object_description": record.get("objetoCompra"),
        "estimated_value": record.get("valorTotalEstimado"),
        "published_at": parse_timestamp(record.get("dataPublicacaoPncp")),
        "proposals_close_at": parse_timestamp(record.get("dataEncerramentoProposta")),
    }


def fetch_with_retry(
    client: PncpClient,
    policy: RetryPolicy,
    sleep: Callable[[float], None],
    **params: object,
) -> TenderPage:
    attempt = 0
    while True:
        try:
            return client.fetch_open_tenders(**params)
        except RETRYABLE_ERRORS:
            attempt += 1
            if attempt >= policy.max_attempts:
                raise
            sleep(policy.delay(attempt - 1))


def start_run(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO collection_runs DEFAULT VALUES RETURNING id")
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn: psycopg.Connection, stats: RunStats) -> None:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE collection_runs SET finished_at = now(), pages = %s, tenders_new = %s, "
            "tenders_seen = %s, errors = %s WHERE id = %s",
            (stats.pages, stats.tenders_new, stats.tenders_seen, Jsonb(stats.errors), stats.run_id),
        )
    conn.commit()


def store_page(
    conn: psycopg.Connection, records: list[dict], state: str, page_number: int, stats: RunStats
) -> None:
    for record in records:
        stats.tenders_seen += 1
        try:
            values = parse_tender(record)
        except MalformedRecordError as exc:
            stats.errors.append(
                {
                    "state": state,
                    "page": page_number,
                    "control_number": record.get("numeroControlePNCP"),
                    "error": str(exc),
                }
            )
            continue
        with conn.cursor() as cur:
            cur.execute(UPSERT_SQL, {**values, "payload": Jsonb(record)})
            row = cur.fetchone()
        if row and row[0]:
            stats.tenders_new += 1
    conn.commit()


def collect_state(
    client: PncpClient,
    conn: psycopg.Connection,
    stats: RunStats,
    state: str,
    *,
    modality_id: int,
    closing_until: date,
    page_size: int,
    pause: float,
    max_pages: int | None,
    retry: RetryPolicy,
    sleep: Callable[[float], None],
    on_page: Callable[[str, TenderPage], None] | None,
) -> None:
    page_number = 1
    while True:
        try:
            page = fetch_with_retry(
                client,
                retry,
                sleep,
                modality_id=modality_id,
                closing_until=closing_until,
                page=page_number,
                page_size=page_size,
                state_code=state,
            )
        except FETCH_ERRORS as exc:
            stats.errors.append({"state": state, "page": page_number, "error": str(exc)})
            return

        stats.pages += 1
        store_page(conn, page.records, state, page_number, stats)
        if on_page:
            on_page(state, page)
        sleep(pause)

        finished = not page.records or page.remaining_pages <= 0
        reached_limit = max_pages is not None and page_number >= max_pages
        if finished or reached_limit:
            return
        page_number += 1


def collect(
    client: PncpClient,
    conn: psycopg.Connection,
    *,
    modality_id: int,
    closing_until: date,
    states: tuple[str, ...] = BRAZILIAN_STATES,
    page_size: int = MAX_PAGE_SIZE,
    pause: float = 1.0,
    max_pages_per_state: int | None = None,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Callable[[float], None] = time.sleep,
    on_page: Callable[[str, TenderPage], None] | None = None,
) -> RunStats:
    stats = RunStats(run_id=start_run(conn))
    try:
        for state in states:
            collect_state(
                client,
                conn,
                stats,
                state,
                modality_id=modality_id,
                closing_until=closing_until,
                page_size=page_size,
                pause=pause,
                max_pages=max_pages_per_state,
                retry=retry,
                sleep=sleep,
                on_page=on_page,
            )
    finally:
        finish_run(conn, stats)
    return stats
