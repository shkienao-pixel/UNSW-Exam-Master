"""Content Guard: clean raw PDF text by removing noise, ads, and irrelevant content."""

from __future__ import annotations

from services.llm_service import LLMProcessor

CONTENT_GUARD_PROMPT = """你是一名学术内容过滤专家。
输入是从 PDF 提取的原始文本，可能含：广告、营销话术、页眉页脚、水课内容、乱码。
任务：仅保留核心学术内容（定义、公式、例题、推导、逻辑框架），删除一切噪音。
只输出清洗后的文本，不要解释，不要注释。"""

CHUNK_SIZE = 12000


class ContentGuard:
    """Clean raw PDF text using LLM to remove noise and retain academic content."""

    def __init__(self) -> None:
        self._llm = LLMProcessor()

    def clean(self, raw_text: str, api_key: str) -> str:
        """
        Clean raw text extracted from PDF.

        Splits text into chunks of CHUNK_SIZE chars when text > 15000 chars.
        Returns the merged cleaned text.
        """
        if not api_key or not api_key.strip():
            return raw_text

        text = raw_text.strip()
        if not text:
            return text

        if len(text) <= 15000:
            return self._clean_chunk(text, api_key)

        # Split into chunks and clean each
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunks.append(text[start:end])
            start = end

        cleaned_parts: list[str] = []
        for chunk in chunks:
            cleaned = self._clean_chunk(chunk, api_key)
            cleaned_parts.append(cleaned)

        return "\n\n".join(cleaned_parts)

    def _clean_chunk(self, chunk: str, api_key: str) -> str:
        user_message = f"请清洗以下学术文本，仅保留核心学术内容：\n\n{chunk}"
        try:
            result = self._llm.invoke(
                CONTENT_GUARD_PROMPT,
                user_message,
                api_key=api_key.strip(),
                temperature=0.1,
            )
            return result.strip() if result else chunk
        except Exception:
            return chunk
