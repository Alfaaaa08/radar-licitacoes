import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from radar.schema import (
    FIELD_NAMES,
    Evidence,
    FieldResult,
    GoldAnnotation,
    SiteVisit,
    SmallBusinessPreference,
    TenderExtraction,
)

EVIDENCE = {"page": 3, "quote": "As propostas serão recebidas até 20/11/2026 às 09h."}


def extraction_json(**overrides) -> dict:
    data = TenderExtraction.blank().model_dump(mode="json")
    data.update(overrides)
    return data


def test_blank_extraction_has_every_field_not_found():
    blank = TenderExtraction.blank()

    assert FIELD_NAMES == (
        "proposal_deadline",
        "estimated_value",
        "requires_technical_certificate",
        "bid_bond_percentage",
        "performance_bond_percentage",
        "site_visit",
        "small_business_preference",
    )
    assert all(getattr(blank, name).status == "not_found" for name in FIELD_NAMES)


def test_found_field_parses_typed_values():
    data = extraction_json(
        proposal_deadline={"status": "found", "value": "2026-11-20T09:00:00", "evidence": EVIDENCE},
        estimated_value={"status": "found", "value": 150000.5, "evidence": EVIDENCE},
        requires_technical_certificate={"status": "found", "value": True, "evidence": EVIDENCE},
        bid_bond_percentage={"status": "found", "value": 1, "evidence": EVIDENCE},
        site_visit={"status": "found", "value": "optional", "evidence": EVIDENCE},
        small_business_preference={"status": "found", "value": "quota", "evidence": EVIDENCE},
    )

    result = TenderExtraction.model_validate_json(json.dumps(data))

    assert result.proposal_deadline.value == datetime(2026, 11, 20, 9, 0)
    assert result.estimated_value.value == Decimal("150000.5")
    assert result.requires_technical_certificate.value is True
    assert result.bid_bond_percentage.value == Decimal(1)
    assert result.site_visit.value is SiteVisit.OPTIONAL
    assert result.small_business_preference.value is SmallBusinessPreference.QUOTA


def test_found_field_without_evidence_is_rejected():
    with pytest.raises(ValidationError, match="needs evidence"):
        FieldResult[bool](status="found", value=True)


def test_found_field_without_value_is_rejected():
    with pytest.raises(ValidationError, match="needs a value"):
        FieldResult[bool](status="found", evidence=Evidence(**EVIDENCE))


def test_not_found_field_must_be_empty():
    with pytest.raises(ValidationError, match="no value and no evidence"):
        FieldResult[bool](status="not_found", value=False)


def test_false_is_a_valid_found_value():
    result = FieldResult[bool](status="found", value=False, evidence=Evidence(**EVIDENCE))

    assert result.value is False


def test_zero_percentage_is_a_valid_found_value():
    data = extraction_json(
        bid_bond_percentage={"status": "found", "value": 0, "evidence": EVIDENCE}
    )

    assert TenderExtraction.model_validate_json(json.dumps(data)).bid_bond_percentage.value == 0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("proposal_deadline", "2026-11-20"),
        ("proposal_deadline", "not a date"),
        ("estimated_value", -1),
        ("bid_bond_percentage", 101),
        ("performance_bond_percentage", -5),
        ("requires_technical_certificate", 1),
        ("requires_technical_certificate", "yes"),
        ("site_visit", "mandatory"),
        ("small_business_preference", "all"),
    ],
)
def test_invalid_values_are_rejected(name, value):
    data = extraction_json(**{name: {"status": "found", "value": value, "evidence": EVIDENCE}})

    with pytest.raises(ValidationError):
        TenderExtraction.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("page", [0, -1])
def test_evidence_page_starts_at_one(page):
    with pytest.raises(ValidationError):
        Evidence(page=page, quote="text")


def test_empty_and_oversized_quotes_are_rejected():
    with pytest.raises(ValidationError):
        Evidence(page=1, quote="")
    with pytest.raises(ValidationError):
        Evidence(page=1, quote="x" * 501)


def test_unknown_fields_are_rejected_to_catch_typos():
    data = extraction_json(proposal_dedline={"status": "not_found"})

    with pytest.raises(ValidationError):
        TenderExtraction.model_validate_json(json.dumps(data))


def test_annotation_round_trips_through_json():
    annotation = GoldAnnotation(
        control_number="00000000000100-1-000001/2026",
        document_sequence=1,
        annotator="theo",
        annotated_on=date(2026, 11, 15),
        extraction=TenderExtraction.blank(),
        notes="blank",
    )

    restored = GoldAnnotation.model_validate_json(annotation.model_dump_json())

    assert restored == annotation
