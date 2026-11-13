from fakes import CLOSING_UNTIL, ScriptedClient, make_page, make_record

from radar.collector import RetryPolicy, collect
from radar.pncp import ServerError

FAST_RETRY = RetryPolicy(max_attempts=2, base_delay=0.0)


def run_collect(client, conn, states=("SP",), **kwargs):
    return collect(
        client,
        conn,
        modality_id=6,
        closing_until=CLOSING_UNTIL,
        states=states,
        pause=0.0,
        retry=FAST_RETRY,
        sleep=lambda seconds: None,
        **kwargs,
    )


def count_tenders(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tenders")
        return cur.fetchone()[0]


def fetch_run(conn, run_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT finished_at IS NOT NULL, pages, tenders_new, tenders_seen, errors "
            "FROM collection_runs WHERE id = %s",
            (run_id,),
        )
        return cur.fetchone()


def single_page_client(records, state="SP"):
    return ScriptedClient({state: [make_page(records, 1, 1)]})


def test_collect_stores_tenders_and_records_the_run(db_conn):
    client = single_page_client([make_record(1), make_record(2)])

    stats = run_collect(client, db_conn)

    assert (stats.pages, stats.tenders_seen, stats.tenders_new) == (1, 2, 2)
    assert count_tenders(db_conn) == 2
    finished, pages, new, seen, errors = fetch_run(db_conn, stats.run_id)
    assert (finished, pages, new, seen, errors) == (True, 1, 2, 2, [])


def test_collect_is_idempotent(db_conn):
    records = [make_record(1), make_record(2)]

    first = run_collect(single_page_client(records), db_conn)
    second = run_collect(single_page_client(records), db_conn)

    assert first.tenders_new == 2
    assert second.tenders_new == 0
    assert second.tenders_seen == 2
    assert count_tenders(db_conn) == 2


def test_collect_updates_changed_tenders_without_duplicating(db_conn):
    run_collect(single_page_client([make_record(1)]), db_conn)

    changed = make_record(1, objetoCompra="Changed object")
    stats = run_collect(single_page_client([changed]), db_conn)

    assert stats.tenders_new == 0
    assert count_tenders(db_conn) == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT object_description, payload->>'objetoCompra' FROM tenders")
        assert cur.fetchone() == ("Changed object", "Changed object")


def test_collect_follows_pagination_until_the_last_page(db_conn):
    client = ScriptedClient(
        {
            "SP": [
                make_page([make_record(1), make_record(2)], 1, 3),
                make_page([make_record(3), make_record(4)], 2, 3),
                make_page([make_record(5)], 3, 3),
            ]
        }
    )

    stats = run_collect(client, db_conn)

    assert client.calls == [("SP", 1), ("SP", 2), ("SP", 3)]
    assert stats.pages == 3
    assert count_tenders(db_conn) == 5


def test_collect_respects_max_pages_per_state(db_conn):
    client = ScriptedClient(
        {"SP": [make_page([make_record(1)], 1, 5), make_page([make_record(2)], 2, 5)]}
    )

    stats = run_collect(client, db_conn, max_pages_per_state=2)

    assert stats.pages == 2
    assert count_tenders(db_conn) == 2


def test_collect_covers_every_requested_state(db_conn):
    client = ScriptedClient(
        {
            "SP": [make_page([make_record(1, "SP")], 1, 1)],
            "MG": [make_page([make_record(2, "MG")], 1, 1)],
        }
    )

    run_collect(client, db_conn, states=("SP", "MG"))

    with db_conn.cursor() as cur:
        cur.execute("SELECT state_code FROM tenders ORDER BY state_code")
        assert [row[0] for row in cur.fetchall()] == ["MG", "SP"]


def test_failing_state_is_recorded_and_does_not_stop_the_others(db_conn):
    client = ScriptedClient(
        {
            "SP": [ServerError("500")] * 2,
            "MG": [make_page([make_record(2, "MG")], 1, 1)],
        }
    )

    stats = run_collect(client, db_conn, states=("SP", "MG"))

    assert count_tenders(db_conn) == 1
    assert len(stats.errors) == 1
    assert stats.errors[0]["state"] == "SP"
    assert stats.errors[0]["page"] == 1
    _, _, _, _, stored_errors = fetch_run(db_conn, stats.run_id)
    assert stored_errors[0]["state"] == "SP"


def test_malformed_record_is_skipped_and_reported(db_conn):
    records = [make_record(1), make_record(2, anoCompra=None), make_record(3)]

    stats = run_collect(single_page_client(records), db_conn)

    assert stats.tenders_seen == 3
    assert stats.tenders_new == 2
    assert count_tenders(db_conn) == 2
    assert len(stats.errors) == 1
    assert "anoCompra" in stats.errors[0]["error"]


def test_empty_state_is_not_an_error(db_conn):
    client = ScriptedClient({"SP": [make_page([], 1, 0)]})

    stats = run_collect(client, db_conn)

    assert stats.errors == []
    assert stats.pages == 1
    assert count_tenders(db_conn) == 0


def test_run_is_finished_even_when_collection_is_interrupted(db_conn):
    client = ScriptedClient({"SP": [KeyboardInterrupt()]})

    try:
        run_collect(client, db_conn)
    except KeyboardInterrupt:
        pass

    with db_conn.cursor() as cur:
        cur.execute("SELECT finished_at IS NOT NULL FROM collection_runs")
        assert cur.fetchone()[0] is True
