"""
PDF and document processing services.
"""

import io
from typing import Any

from pypdf import PdfReader


class PDFProcessor:
    """Extracts text from PDF files."""

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
        try:
            data = uploaded_file.read()
        except Exception as e:
            raise ValueError(f"无法读取文件：{e!s}") from e

        if not data or len(data) == 0:
            raise ValueError("文件为空，无法提取内容。")

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            raise ValueError(f"无法解析 PDF（文件可能已损坏）：{e!s}") from e

        parts: list[str] = []
        try:
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
        except Exception as e:
            raise ValueError(f"提取页面文本时出错：{e!s}") from e

        return "\n".join(parts)
