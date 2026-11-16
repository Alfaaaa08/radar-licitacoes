from dataclasses import dataclass
from pathlib import Path

import pymupdf

MIN_CHARS_PER_PAGE = 50
SCANNED_PAGE_RATIO = 0.5


class PdfError(Exception):
    pass


@dataclass(frozen=True)
class ExtractedText:
    pages: list[str]
    status: str

    @property
    def char_count(self) -> int:
        return sum(len(page) for page in self.pages)


def clean_text(text: str) -> str:
    return text.replace("\x00", "")


def classify_pages(pages: list[str]) -> str:
    nearly_empty = sum(1 for page in pages if len(page.strip()) < MIN_CHARS_PER_PAGE)
    return "scanned" if nearly_empty / len(pages) >= SCANNED_PAGE_RATIO else "text"


def extract_text(path: Path) -> ExtractedText:
    try:
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise PdfError("PDF is password protected")
            pages = [clean_text(page.get_text()) for page in document]
    except PdfError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise PdfError(f"could not read PDF: {exc}") from exc

    if not pages:
        raise PdfError("PDF has no pages")
    return ExtractedText(pages=pages, status=classify_pages(pages))
