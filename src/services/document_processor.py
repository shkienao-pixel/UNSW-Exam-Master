"""
PDF and document processing services.
"""

import io
from typing import Any

from pypdf import PdfReader


class PDFProcessor:
    """Extracts text from PDF files."""

    def _read_bytes(self, uploaded_file: Any) -> bytes:
        """Read raw bytes from a file-like object."""
        try:
            data = uploaded_file.read()
        except Exception as e:
            raise ValueError(f"Unable to read file: {e!s}") from e

        if not data or len(data) == 0:
            raise ValueError("File is empty and cannot be processed.")
        return data

    def extract_pages_from_bytes(self, data: bytes) -> list[dict[str, Any]]:
        """
        Extract per-page text from PDF bytes.

        Returns:
            List of {"page": int, "text": str}.
        """
        if not data:
            raise ValueError("File is empty and cannot be processed.")

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            raise ValueError(f"Unable to parse PDF (possibly corrupted): {e!s}") from e

        pages: list[dict[str, Any]] = []
        try:
            for idx, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append({"page": idx + 1, "text": text})
        except Exception as e:
            raise ValueError(f"Error extracting page text: {e!s}") from e

        return pages

    def extract_pages(self, uploaded_file: Any) -> list[dict[str, Any]]:
        """Read an uploaded file and return extracted per-page text."""
        data = self._read_bytes(uploaded_file)
        return self.extract_pages_from_bytes(data)

    def extract_text(self, uploaded_file: Any) -> str:
        """
        Read an uploaded file and extract text from all pages.

        Args:
            uploaded_file: A file-like object (e.g. Streamlit UploadedFile)
                with .read() returning bytes.

        Returns:
            Concatenated text from all pages.

        Raises:
            ValueError: If the file is empty, corrupted, or cannot be read.
        """
        pages = self.extract_pages(uploaded_file)
        return "\n".join(p["text"] for p in pages)
