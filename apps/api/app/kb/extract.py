"""从资料里抽出可供检索的纯文本。抽不到就返回空。"""

from __future__ import annotations

import io
from pathlib import Path


_MAX_CHARS = 20000


def extract_search_text(file_name: str, data: bytes) -> str:
    """按后缀抽正文，失败返回空字符串。"""

    suffix = Path(file_name or "").suffix.lower()
    text = ""
    try:
        if suffix in {".txt", ".md", ".csv", ".log", ".json", ".yaml", ".yml", ".ini"}:
            text = data.decode("utf-8", errors="ignore")
        elif suffix == ".docx":
            text = _from_docx(data)
        elif suffix == ".pdf":
            text = _from_pdf(data)
    except Exception:
        text = ""
    return " ".join(text.split())[:_MAX_CHARS]


def _from_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages[:40]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)
