import json

from radar.gold import fetch_candidates, load_pages, select_candidates, validate_annotation_file

CNPJ = "00000000000100"


def add_tender(conn, number, sphere="M", state="SP", terms=("software",), pages=("page",) * 5):
    control_number = f"{CNPJ}-1-{number:06d}/2026"
    payload = json.dumps({"orgaoEntidade": {"esferaId": sphere}})
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenders (pncp_control_number, agency_cnpj, purchase_year, "
            "purchase_sequence, state_code, object_description, payload, it_matched_terms) "
            "VALUES (%s, %s, 2026, %s, %s, %s, %s, %s)",
            (control_number, CNPJ, number, state, f"Object {number}", payload, list(terms)),
        )
        if pages is not None:
            cur.execute(
                "INSERT INTO tender_documents (pncp_control_number, document_sequence, payload, "
                "download_status, text_status, page_count) "
                "VALUES (%s, 1, '{}', 'downloaded', 'text', %s) RETURNING id",
                (control_number, len(pages)),
            )
            document_id = cur.fetchone()[0]
            for index, text in enumerate(pages, start=1):
                cur.execute(
                    "INSERT INTO document_pages (document_id, page_number, text) "
                    "VALUES (%s, %s, %s)",
                    (document_id, index, text),
                )
    conn.commit()
    return control_number


def test_candidates_require_it_match_text_and_enough_pages(db_conn):
    good = add_tender(db_conn, 1)
    add_tender(db_conn, 2, terms=())
    add_tender(db_conn, 3, pages=None)
    add_tender(db_conn, 4, pages=("a", "b"))

    candidates = fetch_candidates(db_conn)

    assert [c.control_number for c in candidates] == [good]
    assert candidates[0].sphere == "municipal"
    assert candidates[0].state == "SP"
    assert candidates[0].page_count == 5


def test_scanned_documents_are_not_candidates(db_conn):
    number = add_tender(db_conn, 1)
    with db_conn.cursor() as cur:
        cur.execute("UPDATE tender_documents SET text_status = 'scanned'")
    db_conn.commit()

    assert number not in [c.control_number for c in fetch_candidates(db_conn)]


def test_sphere_codes_map_to_groups(db_conn):
    for number, code in enumerate(["F", "E", "D", "M", "X"], start=1):
        add_tender(db_conn, number, sphere=code)

    spheres = sorted(c.sphere for c in fetch_candidates(db_conn))

    assert spheres == ["federal", "municipal", "other", "state", "state"]


def test_seed_changes_the_order_but_not_the_set(db_conn):
    for number in range(1, 9):
        add_tender(db_conn, number)

    first = [c.control_number for c in fetch_candidates(db_conn, seed="1")]
    second = [c.control_number for c in fetch_candidates(db_conn, seed="2")]

    assert sorted(first) == sorted(second)
    assert first != second
    assert first == [c.control_number for c in fetch_candidates(db_conn, seed="1")]


def test_end_to_end_selection_from_the_database(db_conn):
    states = ["SP", "MG", "RJ", "BA", "PR", "RS", "SC", "GO", "PE", "CE"]
    number = 0
    for sphere in ("F", "E", "M"):
        for state in states:
            number += 1
            add_tender(db_conn, number, sphere=sphere, state=state)

    selected = select_candidates(fetch_candidates(db_conn))

    assert len(selected) == 20


def test_load_pages_returns_pages_in_order(db_conn):
    number = add_tender(db_conn, 1, pages=("first", "second", "third"))

    assert load_pages(db_conn, number, 1) == ["first", "second", "third"]
    assert load_pages(db_conn, number, 2) == []


def write_annotation_file(tmp_path, number, quote, page=2):
    evidence = {"page": page, "quote": quote}
    data = {
        "control_number": number,
        "document_sequence": 1,
        "annotator": "theo",
        "annotated_on": "2026-11-15",
        "extraction": {
            "proposal_deadline": {"status": "not_found", "value": None, "evidence": None},
            "estimated_value": {"status": "not_found", "value": None, "evidence": None},
            "requires_technical_certificate": {
                "status": "found",
                "value": True,
                "evidence": evidence,
            },
            "bid_bond_percentage": {"status": "not_found", "value": None, "evidence": None},
            "performance_bond_percentage": {"status": "not_found", "value": None, "evidence": None},
            "site_visit": {"status": "not_found", "value": None, "evidence": None},
            "small_business_preference": {"status": "not_found", "value": None, "evidence": None},
        },
        "notes": "",
    }
    path = tmp_path / "annotation.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_annotation_has_no_issues(db_conn, tmp_path):
    number = add_tender(db_conn, 1, pages=("intro", "Exige atestado de capacidade técnica.", "end"))
    path = write_annotation_file(tmp_path, number, "exige atestado de capacidade tecnica")

    assert validate_annotation_file(db_conn, path) == []


def test_annotation_with_a_quote_that_is_not_on_the_page_is_reported(db_conn, tmp_path):
    number = add_tender(db_conn, 1, pages=("intro", "Exige atestado.", "end"))
    path = write_annotation_file(tmp_path, number, "dispensa atestado")

    issues = validate_annotation_file(db_conn, path)

    assert issues == ["requires_technical_certificate: quote not found on page 2"]


def test_annotation_for_a_tender_without_stored_text_is_reported(db_conn, tmp_path):
    path = write_annotation_file(tmp_path, "missing-1/2026", "anything")

    issues = validate_annotation_file(db_conn, path)

    assert "no text stored" in issues[0]


def test_schema_errors_are_reported_with_the_field_path(db_conn, tmp_path):
    number = add_tender(db_conn, 1)
    path = write_annotation_file(tmp_path, number, "page")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["extraction"]["site_visit"] = {"status": "found", "value": "optional", "evidence": None}
    path.write_text(json.dumps(data), encoding="utf-8")

    issues = validate_annotation_file(db_conn, path)

    assert any("site_visit" in issue and "evidence" in issue for issue in issues)


def test_invalid_json_is_reported(db_conn, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    issues = validate_annotation_file(db_conn, path)

    assert issues[0].startswith("invalid JSON") or "json" in issues[0].lower()
