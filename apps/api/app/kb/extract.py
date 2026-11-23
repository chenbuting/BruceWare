"""从资料里抽出可供检索的纯文本。抽不到就返回空。"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path


_MAX_CHARS = 20000
_SHEET_MAX_CHARS = 40000
_SHEET_ROWS = 500
_SHEET_SHEETS = 8

_TEXT_SUFFIXES = {".txt", ".md", ".log", ".json", ".yaml", ".yml", ".ini"}
_SHEET_SUFFIXES = {".csv", ".xlsx", ".xls"}


def is_sheet_name(file_name: str) -> bool:
    """是不是表格文件。"""

    return Path(file_name or "").suffix.lower() in _SHEET_SUFFIXES


def extract_search_text(file_name: str, data: bytes, *, collapse: bool = True) -> str:
    """按后缀抽正文，失败返回空字符串。collapse=False 时保留换行，给预览用。"""

    suffix = Path(file_name or "").suffix.lower()
    text = ""
    try:
        if suffix in _TEXT_SUFFIXES:
            text = _decode_text(data)
        elif suffix == ".csv":
            text = _from_csv(data)
        elif suffix == ".xlsx":
            text = _from_xlsx(data)
        elif suffix == ".xls":
            text = _from_xls(data)
        elif suffix == ".docx":
            text = _from_docx(data)
        elif suffix == ".pdf":
            text = _from_pdf(data)
    except Exception:
        text = ""
    limit = _SHEET_MAX_CHARS if suffix in _SHEET_SUFFIXES else _MAX_CHARS
    if collapse:
        return " ".join(text.split())[:limit]
    return text[:limit]


def _decode_text(data: bytes) -> str:
    """先按 UTF-8，不行再按国标。避免 CSV 按错编码变成乱码。"""

    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("gb18030", errors="replace")


def _join_cells(cells: list[str]) -> str:
    return " | ".join(item for item in cells if item)


def _from_csv(data: bytes) -> str:
    text = _decode_text(data)
    reader = csv.reader(io.StringIO(text))
    lines: list[str] = []
    for index, row in enumerate(reader):
        if index >= _SHEET_ROWS:
            break
        line = _join_cells([str(cell).strip() for cell in row])
        if line:
            lines.append(line)
    return "\n".join(lines) or text


def _from_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for sheet in book.worksheets[:_SHEET_SHEETS]:
            if sheet.title:
                lines.append(str(sheet.title).strip())
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index >= _SHEET_ROWS:
                    break
                line = _join_cells([str(cell).strip() for cell in row if cell is not None])
                if line:
                    lines.append(line)
    finally:
        book.close()
    return "\n".join(lines)


def _from_xls(data: bytes) -> str:
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    lines: list[str] = []
    for sheet in book.sheets()[:_SHEET_SHEETS]:
        if sheet.name:
            lines.append(str(sheet.name).strip())
        for index in range(min(sheet.nrows, _SHEET_ROWS)):
            line = _join_cells([str(sheet.cell_value(index, col)).strip() for col in range(sheet.ncols)])
            if line:
                lines.append(line)
    return "\n".join(lines)


def _from_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


_SHEET_COLS = 30
_CELL_LEN = 80


def _clip_cell(value: object) -> str:
    """格子收成短文本。空值丢掉。"""

    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "none":
        return ""
    return text[:_CELL_LEN]


def _grid_rows(raw_rows: list[list[object]]) -> list[list[str]]:
    """限制列数，整行都空的不要。"""

    rows: list[list[str]] = []
    for raw in raw_rows:
        cells = [_clip_cell(item) for item in raw[:_SHEET_COLS]]
        if any(cells):
            rows.append(cells)
    return rows


def _grid_of(file_name: str, data: bytes) -> list[dict]:
    """按文件类型抽出工作表。失败由调用方接住。"""

    suffix = Path(file_name or "").suffix.lower()
    if suffix == ".csv":
        text = _decode_text(data)
        reader = csv.reader(io.StringIO(text))
        raw: list[list[object]] = []
        for index, row in enumerate(reader):
            if index >= _SHEET_ROWS:
                break
            raw.append(list(row))
        rows = _grid_rows(raw)
        return [{"name": "", "rows": rows}] if rows else []
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets: list[dict] = []
        try:
            for sheet in book.worksheets[:_SHEET_SHEETS]:
                raw = []
                for index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if index >= _SHEET_ROWS:
                        break
                    raw.append(list(row))
                rows = _grid_rows(raw)
                if rows:
                    sheets.append({"name": str(sheet.title or "").strip(), "rows": rows})
        finally:
            book.close()
        return sheets
    if suffix == ".xls":
        import xlrd

        book = xlrd.open_workbook(file_contents=data)
        sheets = []
        for sheet in book.sheets()[:_SHEET_SHEETS]:
            raw = []
            for index in range(min(sheet.nrows, _SHEET_ROWS)):
                raw.append([sheet.cell_value(index, col) for col in range(min(sheet.ncols, _SHEET_COLS))])
            rows = _grid_rows(raw)
            if rows:
                sheets.append({"name": str(sheet.name or "").strip(), "rows": rows})
        return sheets
    return []


def extract_sheet_grid(file_name: str, data: bytes) -> str:
    """抽出表格格子的 JSON。失败返回空，调用方继续用原来的正文。"""

    if not is_sheet_name(file_name):
        return ""
    try:
        sheets = _grid_of(file_name, data)
    except Exception:
        return ""
    if not sheets:
        return ""
    import json

    return json.dumps({"sheets": sheets}, ensure_ascii=False)


def _row_matches(blob: str, terms: list[str]) -> bool:
    """中文按包含。数字必须整段对上，避免 48 撞上 4804。"""

    for term in terms:
        if term.isdigit():
            if re.search(rf"(?<!\d){re.escape(term)}(?!\d)", blob):
                return True
        elif term in blob:
            return True
    return False


def sheet_rows_for_ask(grid_json: str, question: str, limit: int = 12) -> str:
    """挑出和问句对得上的格子行。对不上返回空，回答仍用原来的正文。"""

    if not (grid_json or "").strip() or not (question or "").strip():
        return ""
    import json

    from app.kb.search import search_terms

    try:
        data = json.loads(grid_json)
    except json.JSONDecodeError:
        return ""
    sheets = data.get("sheets") if isinstance(data, dict) else None
    if not isinstance(sheets, list):
        return ""
    terms = [item.lower() for item in search_terms(question)]
    if not terms:
        return ""
    blocks: list[str] = []
    left = limit
    for sheet in sheets:
        if left <= 0 or not isinstance(sheet, dict):
            break
        rows = sheet.get("rows")
        if not isinstance(rows, list) or not rows:
            continue
        header = rows[0] if isinstance(rows[0], list) else []
        picked: list[tuple[int, list[str]]] = []
        for index, row in enumerate(rows[1:], start=2):
            if not isinstance(row, list):
                continue
            blob = " ".join(str(cell) for cell in row).lower()
            if _row_matches(blob, terms):
                picked.append((index, [str(cell) for cell in row]))
        if not picked:
            continue
        name = str(sheet.get("name") or "").strip()
        lines = [f"工作表：{name}" if name else "工作表"]
        if header:
            lines.append("表头：" + _join_cells([str(cell) for cell in header]))
        for index, row in picked[:left]:
            lines.append(f"第{index}行：" + _join_cells(row))
        left -= len(picked[:left])
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return "【表格格子】金额、编号以这里的格子为准，不要从旁边正文猜。\n" + "\n\n".join(blocks)


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
