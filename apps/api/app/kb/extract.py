"""从资料里抽出可供检索的纯文本。抽不到就返回空。"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from app.kb.clean import clean_text


_MAX_CHARS = 20000
_SHEET_MAX_CHARS = 40000
_SHEET_ROWS = 500
_SHEET_SHEETS = 8

_TEXT_SUFFIXES = {".txt", ".md", ".log", ".json", ".yaml", ".yml", ".ini"}
_SHEET_SUFFIXES = {".csv", ".xlsx", ".xls"}


def is_sheet_name(file_name: str) -> bool:
    """是不是表格文件。"""

    return Path(file_name or "").suffix.lower() in _SHEET_SUFFIXES


class ParseChoiceError(ValueError):
    """页码、表名或列名没写对。这份正文先不改。"""


def extract_search_text(
    file_name: str,
    data: bytes,
    *,
    collapse: bool = True,
    text_limit: int | None = None,
    sheet_limit: int | None = None,
    sheet_rows: int | None = None,
    sheet_sheets: int | None = None,
    mode: str = "standard",
    hint: str = "",
) -> str:
    """按后缀抽正文，失败返回空字符串。collapse=False 时保留换行，给预览用。"""

    suffix = Path(file_name or "").suffix.lower()
    rows = sheet_rows or _SHEET_ROWS
    sheets = sheet_sheets or _SHEET_SHEETS
    text = ""
    try:
        picked = _extract_mode(suffix, data, mode, hint, rows, sheets)
        if picked is not None:
            text = picked
        elif suffix in _TEXT_SUFFIXES:
            text = _decode_text(data)
        elif suffix == ".csv":
            text = _from_csv(data, rows)
        elif suffix == ".xlsx":
            text = _from_xlsx(data, rows, sheets)
        elif suffix == ".xls":
            text = _from_xls(data, rows, sheets)
        elif suffix == ".docx":
            text = _from_docx(data)
        elif suffix == ".pdf":
            text = _from_pdf(data)
    except ParseChoiceError:
        raise
    except Exception:
        text = ""
    if suffix in _SHEET_SUFFIXES:
        limit = sheet_limit or _SHEET_MAX_CHARS
    else:
        limit = text_limit or _MAX_CHARS
    if collapse:
        return clean_text(text, limit)
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


def _from_csv(data: bytes, sheet_rows: int = _SHEET_ROWS) -> str:
    text = _decode_text(data)
    reader = csv.reader(io.StringIO(text))
    lines: list[str] = []
    for index, row in enumerate(reader):
        if index >= sheet_rows:
            break
        line = _join_cells([str(cell).strip() for cell in row])
        if line:
            lines.append(line)
    return "\n".join(lines) or text


def _from_xlsx(data: bytes, sheet_rows: int = _SHEET_ROWS, sheet_sheets: int = _SHEET_SHEETS) -> str:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for sheet in book.worksheets[:sheet_sheets]:
            if sheet.title:
                lines.append(str(sheet.title).strip())
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index >= sheet_rows:
                    break
                line = _join_cells([str(cell).strip() for cell in row if cell is not None])
                if line:
                    lines.append(line)
    finally:
        book.close()
    return "\n".join(lines)


def _from_xls(data: bytes, sheet_rows: int = _SHEET_ROWS, sheet_sheets: int = _SHEET_SHEETS) -> str:
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    lines: list[str] = []
    for sheet in book.sheets()[:sheet_sheets]:
        if sheet.name:
            lines.append(str(sheet.name).strip())
        for index in range(min(sheet.nrows, sheet_rows)):
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


def _grid_of(file_name: str, data: bytes, sheet_rows: int = _SHEET_ROWS, sheet_sheets: int = _SHEET_SHEETS) -> list[dict]:
    """按文件类型抽出工作表。失败由调用方接住。"""

    suffix = Path(file_name or "").suffix.lower()
    if suffix == ".csv":
        text = _decode_text(data)
        reader = csv.reader(io.StringIO(text))
        raw: list[list[object]] = []
        for index, row in enumerate(reader):
            if index >= sheet_rows:
                break
            raw.append(list(row))
        rows = _grid_rows(raw)
        return [{"name": "", "rows": rows}] if rows else []
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets: list[dict] = []
        try:
            for sheet in book.worksheets[:sheet_sheets]:
                raw = []
                for index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if index >= sheet_rows:
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
        for sheet in book.sheets()[:sheet_sheets]:
            raw = []
            for index in range(min(sheet.nrows, sheet_rows)):
                raw.append([sheet.cell_value(index, col) for col in range(min(sheet.ncols, _SHEET_COLS))])
            rows = _grid_rows(raw)
            if rows:
                sheets.append({"name": str(sheet.name or "").strip(), "rows": rows})
        return sheets
    return []


def extract_sheet_grid(
    file_name: str,
    data: bytes,
    sheet_rows: int | None = None,
    sheet_sheets: int | None = None,
    only_name: str = "",
    only_cols: str = "",
    first_only: bool = False,
) -> str:
    """抽出表格格子的 JSON。失败返回空，调用方继续用原来的正文。"""

    if not is_sheet_name(file_name):
        return ""
    try:
        sheets = _grid_of(file_name, data, sheet_rows or _SHEET_ROWS, sheet_sheets or _SHEET_SHEETS)
    except Exception:
        return ""
    if first_only:
        sheets = sheets[:1]
    name = only_name.strip()
    if name:
        sheets = [item for item in sheets if str(item.get("name") or "").strip() == name]
    col_names = _hint_names(only_cols)
    if col_names:
        kept: list[dict] = []
        for item in sheets:
            rows = item.get("rows") if isinstance(item, dict) else None
            picked = _keep_named_cols(rows if isinstance(rows, list) else [], col_names)
            if picked:
                kept.append({**item, "rows": picked})
        sheets = kept
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


def _extract_mode(suffix: str, data: bytes, mode: str, hint: str, rows: int, sheets: int) -> str | None:
    """特殊抽法。返回 None 表示还按原来的标准抽出。"""

    if mode in {"", "standard", "head"}:
        return None
    if mode == "word_both" and suffix == ".docx":
        return _from_docx_parts(data, True, True)
    if mode == "word_table" and suffix == ".docx":
        return _from_docx_parts(data, False, True)
    if mode == "pdf_pages" and suffix == ".pdf":
        return _from_pdf_pages(data, hint)
    if mode == "sheet_first" and suffix in _SHEET_SUFFIXES:
        return _sheet_text(suffix, data, rows, 1, "", [])
    if mode == "sheet_name" and suffix in {".xlsx", ".xls"}:
        name = hint.strip()
        if not name:
            raise ParseChoiceError("先写表名")
        return _sheet_text(suffix, data, rows, sheets, name, [])
    if mode == "sheet_cols" and suffix in _SHEET_SUFFIXES:
        names = _hint_names(hint)
        if not names:
            raise ParseChoiceError("先写列名，用逗号分开")
        return _sheet_text(suffix, data, rows, sheets, "", names)
    if mode == "text_utf8" and suffix in _TEXT_SUFFIXES:
        return data.decode("utf-8-sig", errors="replace")
    if mode == "text_gb" and suffix in _TEXT_SUFFIXES:
        return data.decode("gb18030", errors="replace")
    return None


def _hint_names(hint: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，、]", hint or "") if part.strip()]


def _from_docx_parts(data: bytes, paragraphs: bool, tables: bool) -> str:
    """Word 可以只要段落、只要表格，或两样都要。"""

    from docx import Document

    doc = Document(io.BytesIO(data))
    parts: list[str] = []
    if paragraphs:
        parts.extend(item.text.strip() for item in doc.paragraphs if item.text.strip())
    if tables:
        for table in doc.tables:
            for row in table.rows:
                line = _join_cells([cell.text.strip() for cell in row.cells])
                if line:
                    parts.append(line)
    return "\n".join(parts)


def _sheet_text(suffix: str, data: bytes, rows: int, sheets: int, only_name: str, names: list[str]) -> str:
    """按表名或列名抽表格正文。"""

    if suffix == ".csv":
        blocks = [("", _csv_rows(data, rows))]
    elif suffix == ".xlsx":
        blocks = _xlsx_rows(data, rows, sheets, only_name)
    else:
        blocks = _xls_rows(data, rows, sheets, only_name)
    lines: list[str] = []
    for title, body in blocks:
        lines.extend(_lines_from_rows(title, body, names))
    return "\n".join(lines)


def _csv_rows(data: bytes, sheet_rows: int) -> list[list[str]]:
    reader = csv.reader(io.StringIO(_decode_text(data)))
    rows: list[list[str]] = []
    for index, row in enumerate(reader):
        if index >= sheet_rows:
            break
        rows.append([str(cell).strip() for cell in row])
    return rows


def _xlsx_rows(data: bytes, sheet_rows: int, sheet_sheets: int, only_name: str) -> list[tuple[str, list[list[str]]]]:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[tuple[str, list[list[str]]]] = []
    try:
        chosen = book.worksheets
        if only_name:
            chosen = [sheet for sheet in chosen if str(sheet.title or "").strip() == only_name]
        for sheet in chosen[:sheet_sheets]:
            rows: list[list[str]] = []
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index >= sheet_rows:
                    break
                rows.append(["" if cell is None else str(cell).strip() for cell in row])
            blocks.append((str(sheet.title or "").strip(), rows))
    finally:
        book.close()
    return blocks


def _xls_rows(data: bytes, sheet_rows: int, sheet_sheets: int, only_name: str) -> list[tuple[str, list[list[str]]]]:
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    blocks: list[tuple[str, list[list[str]]]] = []
    chosen = book.sheets()
    if only_name:
        chosen = [sheet for sheet in chosen if str(sheet.name or "").strip() == only_name]
    for sheet in chosen[:sheet_sheets]:
        rows: list[list[str]] = []
        for index in range(min(sheet.nrows, sheet_rows)):
            rows.append([str(sheet.cell_value(index, col)).strip() for col in range(sheet.ncols)])
        blocks.append((str(sheet.name or "").strip(), rows))
    return blocks


def _lines_from_rows(title: str, rows: list[list[str]], names: list[str]) -> list[str]:
    usable = [row for row in rows if any(cell.strip() for cell in row)]
    if not usable:
        return []
    if names:
        usable = _keep_named_cols(usable, names)
        if not usable:
            return []
    lines = [title] if title else []
    for row in usable:
        line = _join_cells([cell.strip() for cell in row])
        if line:
            lines.append(line)
    return lines


def _keep_named_cols(rows: list, names: list[str]) -> list[list[str]]:
    """按第一行的列名留下对应格子。对不上就整表不要。"""

    if not rows or not isinstance(rows[0], list):
        return []
    header = [str(cell).strip() for cell in rows[0]]
    indexes: list[int] = []
    for name in names:
        for index, cell in enumerate(header):
            if cell == name and index not in indexes:
                indexes.append(index)
                break
    if not indexes:
        return []
    picked: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        picked.append([str(row[index]).strip() if index < len(row) else "" for index in indexes])
    return picked


def _page_indexes(hint: str, total: int) -> list[int]:
    """把 1-3,5 收成从 0 开始的页码。写错就报给上面。"""

    found: list[int] = []
    for part in re.split(r"[,，、\s]+", (hint or "").strip()):
        if not part:
            continue
        chunk = part.replace("—", "-")
        try:
            if "-" in chunk:
                left, right = chunk.split("-", 1)
                start, end = int(left), int(right)
                if start > end:
                    start, end = end, start
                found.extend(range(start, end + 1))
            else:
                found.append(int(chunk))
        except ValueError as exc:
            raise ParseChoiceError("页码写成这样：1-3,5") from exc
    indexes: list[int] = []
    for number in found:
        if 1 <= number <= total and number - 1 not in indexes:
            indexes.append(number - 1)
        if len(indexes) >= 40:
            break
    if not indexes:
        raise ParseChoiceError("这些页码在这份里没有，例如 1-3,5")
    return indexes


def _from_pdf_pages(data: bytes, hint: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for index in _page_indexes(hint, len(reader.pages)):
        parts.append(reader.pages[index].extract_text() or "")
    return "\n".join(parts)


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
