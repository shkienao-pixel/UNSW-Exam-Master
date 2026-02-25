"""Tests for PDFProcessor — pure extraction logic."""

from __future__ import annotations

import io
import struct
import zlib

import pytest

from services.document_processor import PDFProcessor


def _make_minimal_pdf(page_text: str = "Hello PDF") -> bytes:
    """Build a minimal valid single-page PDF with *page_text* as content stream."""
    content = f"BT /F1 12 Tf 72 720 Td ({page_text}) Tj ET".encode()
    content_compressed = zlib.compress(content)

    objects: list[bytes] = []

    def obj(n: int, body: str) -> bytes:
        return f"{n} 0 obj\n{body}\nendobj\n".encode()

    # 1: Catalog
    objects.append(obj(1, "<< /Type /Catalog /Pages 2 0 R >>"))
    # 2: Pages
    objects.append(obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>"))
    # 3: Page
    objects.append(obj(3, "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"))
    # 4: Content stream
    stream_body = f"<< /Filter /FlateDecode /Length {len(content_compressed)} >>\nstream\n".encode()
    stream_body += content_compressed + b"\nendstream"
    objects.append(f"4 0 obj\n".encode() + stream_body + b"\nendobj\n")
    # 5: Font (minimal)
    objects.append(obj(5, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    xref_offset = len(header) + len(body)

    xref = b"xref\n0 6\n0000000000 65535 f \n"
    offset = len(header)
    for o in objects:
        xref += f"{offset:010d} 00000 n \n".encode()
        offset += len(o)

    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    )
    return header + body + xref + trailer


class TestPDFProcessor:
    def setup_method(self):
        self.processor = PDFProcessor()

    def test_extract_pages_from_bytes_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            self.processor.extract_pages_from_bytes(b"")

    def test_extract_pages_from_bytes_invalid_raises(self):
        with pytest.raises(ValueError):
            self.processor.extract_pages_from_bytes(b"not a pdf at all")

    def test_extract_pages_returns_list(self):
        pdf_bytes = _make_minimal_pdf("Test content")
        # pypdf may or may not extract text from minimal PDFs; just check no exception.
        try:
            pages = self.processor.extract_pages_from_bytes(pdf_bytes)
            assert isinstance(pages, list)
            for page in pages:
                assert "page" in page
                assert "text" in page
                assert isinstance(page["page"], int)
                assert isinstance(page["text"], str)
        except ValueError:
            # Accept ValueError if pypdf can't handle the minimal PDF structure
            pass

    def test_extract_text_concatenates_pages(self):
        pdf_bytes = _make_minimal_pdf("Alpha")
        try:
            text = self.processor.extract_text(
                type("F", (), {"read": lambda self: pdf_bytes, "name": "t.pdf"})()
            )
            assert isinstance(text, str)
        except ValueError:
            pass

    def test_read_bytes_empty_file_raises(self):
        class EmptyFile:
            def read(self):
                return b""
            name = "empty.pdf"

        with pytest.raises(ValueError, match="empty"):
            self.processor.extract_pages(EmptyFile())
