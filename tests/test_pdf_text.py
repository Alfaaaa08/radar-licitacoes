import pytest
from fakes import LONG_TEXT, make_pdf_bytes

from radar.pdf_text import PdfError, classify_pages, clean_text, extract_text


def write_pdf(tmp_path, pages):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf_bytes(pages))
    return path


def test_extracts_one_text_per_page_in_order(tmp_path):
    path = write_pdf(tmp_path, [f"Page one. {LONG_TEXT}", f"Page two. {LONG_TEXT}"])

    result = extract_text(path)

    assert result.status == "text"
    assert len(result.pages) == 2
    assert result.pages[0].startswith("Page one.")
    assert result.pages[1].startswith("Page two.")
    assert result.char_count == sum(len(page) for page in result.pages)


def test_pdf_without_text_layer_is_marked_scanned(tmp_path):
    path = write_pdf(tmp_path, ["", "", ""])

    assert extract_text(path).status == "scanned"


def test_mostly_blank_pdf_is_marked_scanned(tmp_path):
    path = write_pdf(tmp_path, [LONG_TEXT, "", ""])

    assert extract_text(path).status == "scanned"


def test_mostly_text_pdf_with_a_blank_page_is_text(tmp_path):
    path = write_pdf(tmp_path, [LONG_TEXT, LONG_TEXT, ""])

    assert extract_text(path).status == "text"


def test_corrupt_file_raises_pdf_error(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7 this is not really a pdf")

    with pytest.raises(PdfError):
        extract_text(path)


def test_classify_pages_threshold():
    assert classify_pages(["x" * 100, "x" * 100]) == "text"
    assert classify_pages(["x" * 100, ""]) == "scanned"


def test_clean_text_removes_nul_characters():
    assert clean_text("abc\x00def") == "abcdef"
