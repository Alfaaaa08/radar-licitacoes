from radar.profiling import field_coverage, flatten


def test_flatten_uses_dotted_names_for_nested_objects():
    record = {"id": 1, "agency": {"cnpj": "123", "state": {"code": "SP"}}}

    assert flatten(record) == {"id": 1, "agency.cnpj": "123", "agency.state.code": "SP"}


def test_field_coverage_counts_only_filled_values():
    records = [
        {"id": 1, "note": "a", "agency": {"cnpj": "1"}},
        {"id": 2, "note": "", "agency": {"cnpj": None}},
        {"id": 3, "agency": {"cnpj": "3"}},
    ]

    assert field_coverage(records) == {"agency.cnpj": 2, "id": 3, "note": 1}


def test_zero_and_false_count_as_filled():
    records = [{"value": 0, "flag": False}]

    assert field_coverage(records) == {"flag": 1, "value": 1}
