"""PDF text extraction for uploaded scripts."""

import io

from pypdf import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts and concatenates text from every page of a PDF given as bytes."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages_text).strip()
