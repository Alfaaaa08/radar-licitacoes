from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest
from fakes import CLOSING_UNTIL, FlakyClient, make_page, make_record

from radar.collector import (
    MalformedRecordError,
    RetryPolicy,
    fetch_with_retry,
    parse_tender,
    parse_timestamp,
)
from radar.pncp import PncpError, RateLimitedError, ServerError

BRASILIA = timezone(timedelta(hours=-3))


def test_parse_tender_maps_api_fields_to_columns():
    values = parse_tender(make_record(7, state="MG"))

    assert values == {
        "pncp_control_number": "00000000000100-1-000007/2026",
        "agency_cnpj": "00000000000100",
        "purchase_year": 2026,
        "purchase_sequence": 7,
        "modality_id": 6,
        "state_code": "MG",
        "object_description": "Object 7",
        "estimated_value": 1007.5,
        "published_at": datetime(2026, 11, 1, 10, 0, tzinfo=BRASILIA),
        "proposals_close_at": datetime(2026, 11, 20, 9, 0, tzinfo=BRASILIA),
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"numeroControlePNCP": None},
        {"anoCompra": None},
        {"sequencialCompra": ""},
        {"orgaoEntidade": None},
    ],
)
def test_parse_tender_rejects_records_missing_required_fields(overrides):
    with pytest.raises(MalformedRecordError):
        parse_tender(make_record(1, **overrides))


def test_parse_tender_tolerates_missing_optional_fields():
    record = make_record(1, valorTotalEstimado=None, dataEncerramentoProposta=None)
    record.pop("unidadeOrgao")

    values = parse_tender(record)

    assert values["estimated_value"] is None
    assert values["proposals_close_at"] is None
    assert values["state_code"] is None


def test_parse_timestamp_handles_dates_garbage_and_timezones():
    assert parse_timestamp("2026-11-20") == datetime(2026, 11, 20, tzinfo=BRASILIA)
    assert parse_timestamp("not a date") is None
    assert parse_timestamp(None) is None
    aware = parse_timestamp("2026-11-20T09:00:00+00:00")
    assert aware == datetime(2026, 11, 20, 9, tzinfo=UTC)


def test_retry_delay_doubles_until_the_cap():
    policy = RetryPolicy(base_delay=2.0, max_delay=10.0)

    assert [policy.delay(attempt) for attempt in range(4)] == [2.0, 4.0, 8.0, 10.0]


TEST_POLICY = RetryPolicy(max_attempts=4, base_delay=1.0)


def run_fetch(client, policy=TEST_POLICY):
    sleeps: list[float] = []
    page = fetch_with_retry(
        client,
        policy,
        sleeps.append,
        modality_id=6,
        closing_until=CLOSING_UNTIL,
        page=1,
        page_size=50,
        state_code="SP",
    )
    return page, sleeps


@pytest.mark.parametrize(
    "error",
    [RateLimitedError("429"), ServerError("500"), httpx.ReadTimeout("slow")],
)
def test_fetch_retries_transient_errors_with_growing_delay(error):
    good = make_page([make_record(1)], 1, 1)
    client = FlakyClient([error, error, good])

    page, sleeps = run_fetch(client)

    assert page is good
    assert client.calls == 3
    assert sleeps == [1.0, 2.0]


def test_fetch_gives_up_after_max_attempts():
    client = FlakyClient([ServerError("500")] * 4)

    with pytest.raises(ServerError):
        run_fetch(client)

    assert client.calls == 4


def test_fetch_does_not_retry_client_errors():
    client = FlakyClient([PncpError("400 bad request")])

    with pytest.raises(PncpError):
        run_fetch(client)

    assert client.calls == 1
