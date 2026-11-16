import json
from datetime import date

from radar.gold import (
    Candidate,
    annotation_path,
    blank_annotation,
    find_hints,
    read_selection,
    select_candidates,
    write_annotation,
    write_selection,
)
from radar.schema import GoldAnnotation


def candidate(number: int, sphere: str, state: str) -> Candidate:
    return Candidate(f"c{number:03d}", state, sphere, f"Object {number}", 1, 10)


def pool(spec: dict[str, list[str]]) -> list[Candidate]:
    candidates = []
    for sphere, states in spec.items():
        for state in states:
            candidates.append(candidate(len(candidates), sphere, state))
    return candidates


def count(selected: list[Candidate], sphere: str) -> int:
    return sum(1 for item in selected if item.sphere == sphere)


def test_selection_follows_the_quotas():
    states = ["SP", "MG", "RJ", "BA", "PR", "RS", "SC", "GO", "PE", "CE", "AM", "PA"]
    candidates = pool({"federal": states, "state": states, "municipal": states})

    selected = select_candidates(candidates)

    assert len(selected) == 20
    assert (count(selected, "federal"), count(selected, "state"), count(selected, "municipal")) == (
        6,
        6,
        8,
    )


def test_selection_caps_tenders_per_state_within_each_sphere():
    many = ["SP"] * 10 + ["MG"] * 10 + ["RJ"] * 10 + ["BA"] * 10
    candidates = pool({"federal": many, "state": many, "municipal": many})

    selected = select_candidates(candidates)

    per_sphere_state: dict[tuple[str, str], int] = {}
    for item in selected:
        key = (item.sphere, item.state)
        per_sphere_state[key] = per_sphere_state.get(key, 0) + 1
    assert len(selected) == 20
    assert max(per_sphere_state.values()) <= 2


def test_cap_is_relaxed_when_there_are_too_few_states():
    candidates = pool({"federal": ["SP"] * 10, "state": ["SP"] * 10, "municipal": ["SP"] * 10})

    assert len(select_candidates(candidates)) == 20


def test_short_group_is_topped_up_from_the_others():
    states = ["SP", "MG", "RJ", "BA", "PR", "RS", "SC", "GO", "PE", "CE", "AM", "PA"]
    candidates = pool({"federal": states[:2], "state": states, "municipal": states})

    selected = select_candidates(candidates)

    assert len(selected) == 20
    assert count(selected, "federal") == 2


def test_selection_returns_fewer_when_there_are_not_enough_candidates():
    selected = select_candidates(pool({"federal": ["SP"], "municipal": ["MG"]}))

    assert len(selected) == 2


def test_first_picks_mix_all_spheres():
    states = ["SP", "MG", "RJ", "BA", "PR", "RS", "SC", "GO", "PE", "CE", "AM", "PA"]
    candidates = pool({"federal": states, "state": states, "municipal": states})

    selected = select_candidates(candidates)

    assert {item.sphere for item in selected[:3]} == {"federal", "state", "municipal"}
    assert {item.sphere for item in selected[:5]} == {"federal", "state", "municipal"}


def test_selection_is_deterministic():
    states = ["SP", "MG", "RJ", "BA", "PR", "RS", "SC", "GO"]
    candidates = pool({"federal": states, "state": states, "municipal": states})

    assert select_candidates(candidates) == select_candidates(list(candidates))


def test_selection_file_round_trip(tmp_path):
    selected = [candidate(1, "federal", "SP"), candidate(2, "municipal", "MG")]
    path = tmp_path / "gold" / "selection.json"

    write_selection(path, selected)

    stored = read_selection(path)
    assert [item["order"] for item in stored] == [1, 2]
    assert stored[0]["control_number"] == "c001"
    assert stored[1]["sphere"] == "municipal"
    assert json.loads(path.read_text(encoding="utf-8")) == stored


def test_annotation_path_replaces_slashes():
    path = annotation_path("00394460000141-1-000123/2026")

    assert path.name == "00394460000141-1-000123_2026.json"


def test_blank_annotation_is_written_and_read_back(tmp_path):
    annotation = blank_annotation("c1", 2, "theo", date(2026, 11, 15))
    path = tmp_path / "c1.json"

    write_annotation(path, annotation)

    assert GoldAnnotation.model_validate_json(path.read_text(encoding="utf-8")) == annotation


def test_hints_point_to_pages_and_lines():
    pages = [
        "Introdução\nObjeto: compra de notebooks",
        "Visita técnica: facultativa\nGarantia de execução de 5% do valor",
        "Atestado de capacidade técnica exigido",
    ]

    hints = find_hints(pages)

    assert [(h.page, h.line) for h in hints["site_visit"]] == [(2, "Visita técnica: facultativa")]
    assert hints["performance_bond_percentage"][0].page == 2
    assert hints["requires_technical_certificate"][0].page == 3
    assert hints["bid_bond_percentage"] == []


def test_hints_are_capped_per_field():
    pages = ["visita técnica\n" * 50]

    assert len(find_hints(pages)["site_visit"]) == 8
