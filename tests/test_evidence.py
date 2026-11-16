import pytest

from radar.evidence import check_evidence, normalize_for_match
from radar.schema import Evidence, FieldResult, TenderExtraction

PAGES = [
    "EDITAL\nPregão eletrônico nº 12/2026",
    "5.1  As propostas serão\nrecebidas até 20/11/2026,\nàs 09h00.\n6. VISITA TÉCNICA facultativa",
]


def with_evidence(field: str, quote: str, page: int) -> TenderExtraction:
    blank = TenderExtraction.blank()
    value = {"requires_technical_certificate": True}.get(field, True)
    result = FieldResult[bool](
        status="found", value=value, evidence=Evidence(page=page, quote=quote)
    )
    return blank.model_copy(update={"requires_technical_certificate": result})


def test_blank_extraction_has_no_issues():
    assert check_evidence(TenderExtraction.blank(), PAGES) == []


def test_exact_quote_on_the_cited_page_passes():
    extraction = with_evidence("requires_technical_certificate", "Pregão eletrônico nº 12/2026", 1)

    assert check_evidence(extraction, PAGES) == []


def test_quote_matching_ignores_case_accents_and_line_breaks():
    quote = "as propostas serao recebidas ate 20/11/2026, as 09h00"
    extraction = with_evidence("requires_technical_certificate", quote, 2)

    assert check_evidence(extraction, PAGES) == []


def test_quote_on_the_wrong_page_is_reported():
    extraction = with_evidence("requires_technical_certificate", "visita técnica facultativa", 1)

    issues = check_evidence(extraction, PAGES)

    assert [(i.field, i.message) for i in issues] == [
        ("requires_technical_certificate", "quote not found on page 1")
    ]


def test_invented_quote_is_reported():
    extraction = with_evidence("requires_technical_certificate", "exige garantia de 10%", 2)

    assert len(check_evidence(extraction, PAGES)) == 1


def test_page_beyond_the_document_is_reported():
    extraction = with_evidence("requires_technical_certificate", "anything", 9)

    issues = check_evidence(extraction, PAGES)

    assert "does not exist" in issues[0].message


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  Visita\n  TÉCNICA ", "visita tecnica"), ("a\t\tb", "a b")],
)
def test_normalize_for_match(raw, expected):
    assert normalize_for_match(raw) == expected
