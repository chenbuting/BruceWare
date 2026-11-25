"""按一份原文件出可检查的整理稿。不入库，也不切片、不算向量。"""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

from PIL import Image
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches

from app.kb.assets import _usable_image

_PDF_PAGES = 40
_PARA_LIMIT = 400
_FIGURED = re.compile(r"^图\s*\d+")
_GUIDE_MARK = "【改稿说明】"
_GUIDE = (
    "下面几段只教你怎么改。导入时会整段丢掉，可以留着。",
    "正文：一段写一件事。标题已经加在后面每段开头。一段尽量不要超过400个字。全文超过大约两万字，按主题拆成多份再导入。",
    "Word表格：表留着给你对格子。表下面每一行的句子才会被切片。数字不对就改句子，不要只改格子。空格子不用写。同一行里合并过的格子只出现一次。",
    "图上的字要你自己写。每张图下面空着一行「图1」「图2」。把字写在这一行后面，或另起一段，开头仍写同一个图号。例如：图2 营业收入 123万元",
    "图是扫描出来的表：它还是一张图，不会变成Word表格。每一行写一段，每段都用同一个图号，列名写进句子。例如：图3 利润表 项目 营业收入 金额 123万元",
    "看不清的字写成□，不要猜成看起来合理的数字。还没写的图号可以先空着。",
    "不要调换图片顺序，也不要改图号。图1必须仍是第一张图，否则字会挂错。",
    "补充的字要单独成段，并且段的开头就是「图几」。写在表格格子里、文本框里，或前面还有别的字，就不会挂到图上。",
)


def draft_bytes(file_name: str, data: bytes, on_progress=None) -> tuple[bytes, str]:
    """根据上传内容出一份稿。原文件不改，也不写入知识库。"""

    suffix = Path(file_name or "").suffix.lower()
    if suffix not in {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
        raise ValueError("先出稿只接受 Word、PDF 或图片")
    if not data:
        raise ValueError("文件是空的")
    _tell(on_progress, "正在读取文件", 0, 1)
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"source{suffix}"
        source.write_bytes(data)
        dest, summary = fill_figure_file(source, on_progress)
        return dest.read_bytes(), summary


def fill_figure_file(path: Path, on_progress=None) -> tuple[Path, str]:
    """把版式摆好写到旁边的新文件。原文件不动。返回新路径和一句结果。"""

    source = Path(path)
    if not source.is_file():
        raise ValueError("文件找不到")
    suffix = source.suffix.lower()
    if suffix == ".docx":
        return _fill_docx(source, on_progress)
    if suffix == ".pdf":
        return _fill_pdf(source, on_progress)
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
        return _fill_image(source, on_progress)
    raise ValueError("只处理 Word、PDF 或图片")


def _fill_docx(source: Path, on_progress=None) -> tuple[Path, str]:
    """把 Word 收成普通段落。表格、文本框、标题都写进句子，方便按 400 字切片。"""

    src = Document(str(source))
    if _already_figured(src):
        raise ValueError("这份里已经有图号，没有重复写。请换一份还没写过图号的文件。")
    out = Document()
    _write_guide(out)
    state = _WordDraft(src)
    state.figure_total = _count_blips(src)
    state.on_progress = on_progress
    _tell(on_progress, "正在整理版式", 0, max(state.figure_total, 1))
    for child in src.element.body:
        if child.tag == qn("w:sectPr"):
            continue
        _walk_block(child, state, out)
    _append_side_notes(src, state, out)
    if state.chars == 0 and state.figures == 0:
        raise ValueError("这份 Word 里没有能整理的正文或图")
    _tell(on_progress, "正在写成稿", max(state.figure_total, 1), max(state.figure_total, 1))
    dest = _dest_path(source)
    out.save(str(dest))
    return dest, _word_summary(state)


def _fill_pdf(source: Path, on_progress=None) -> tuple[Path, str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("还没装 PDF 组件") from exc
    try:
        reader = PdfReader(str(source))
    except Exception as exc:
        raise ValueError("这份 PDF 打不开") from exc
    pages = list(reader.pages[:_PDF_PAGES])
    more = len(reader.pages) > _PDF_PAGES
    pictures: list[bytes] = []
    for page in pages:
        try:
            images = page.images
        except Exception:
            continue
        for item in images:
            raw = getattr(item, "data", None)
            if raw and _usable_image(raw):
                pictures.append(raw)
    if not pictures:
        _tell(on_progress, "正在整理文字", 1, 2)
        doc = Document()
        _write_guide(doc)
        wrote = False
        for page in pages:
            for line in (page.extract_text() or "").splitlines():
                text = line.strip()
                if not text:
                    continue
                doc.add_paragraph(text)
                wrote = True
        if not wrote:
            raise ValueError("这份 PDF 里没有能认的图，也没有文字")
        _tell(on_progress, "正在写成稿", 2, 2)
        dest = _dest_path(source)
        doc.save(str(dest))
        note = "这份没有图。稿里是抽出的文字，请按规则改成一段一件事。"
        if more:
            note += "PDF 只处理了前 40 页，后面请另存一份再出稿。"
        return dest, note
    total = len(pictures)
    doc = Document()
    _write_guide(doc)
    for index, raw in enumerate(pictures, start=1):
        _tell(on_progress, f"正在放第 {index} 张图", index - 1, total)
        doc.add_picture(io.BytesIO(_png_bytes(raw)), width=Inches(6.0))
        doc.add_paragraph(f"图{index}")
    _tell(on_progress, "正在写成稿", total, total)
    dest = _dest_path(source)
    doc.save(str(dest))
    return dest, _summary(total, more)


def _fill_image(source: Path, on_progress=None) -> tuple[Path, str]:
    raw = source.read_bytes()
    if not _usable_image(raw):
        raise ValueError("这张图太小，或者打不开")
    _tell(on_progress, "正在放第 1 张图", 0, 1)
    doc = Document()
    _write_guide(doc)
    doc.add_picture(io.BytesIO(_png_bytes(raw)), width=Inches(6.0))
    doc.add_paragraph("图1")
    _tell(on_progress, "正在写成稿", 1, 1)
    dest = _dest_path(source)
    doc.save(str(dest))
    return dest, _summary(1, False)


class _WordDraft:
    """整理一份 Word 时记住标题、图号和已经写过的字。"""

    def __init__(self, src: Document):
        self.src = src
        self.heading = ""
        self.chars = 0
        self.figures = 0
        self.boxes = 0
        self.last = ""
        self.seen_rid: set[str] = set()
        self.figure_total = 0
        self.on_progress = None


_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_NOISE = re.compile(r"^(?:第\s*\d{1,4}\s*页|[-—–.]?\s*\d{1,4}\s*[-—–.]?)$")


def _walk_block(element, state: _WordDraft, out: Document) -> None:
    tag = element.tag
    if tag == qn("w:p"):
        _walk_paragraph(element, state, out)
    elif tag == qn("w:tbl"):
        _walk_table(element, state, out)
    elif tag == qn("w:sdt"):
        content = element.find(qn("w:sdtContent"))
        if content is not None:
            for child in content:
                _walk_block(child, state, out)
    elif tag == qn("w:txbxContent"):
        state.boxes += 1
        for child in element:
            _walk_block(child, state, out)


def _walk_paragraph(element, state: _WordDraft, out: Document) -> None:
    style = _style_val(element)
    if style.upper().startswith("TOC") or "目录" in style:
        return
    buf: list[str] = []

    def flush() -> None:
        text = _tidy("".join(buf))
        buf.clear()
        if not text or _NOISE.match(text) or text.startswith(_GUIDE_MARK):
            return
        if _is_heading(style):
            state.heading = text[:40]
        _emit(out, state, text)

    def walk(node) -> None:
        tag = node.tag
        if tag in {qn("w:del"), qn("w:instrText"), _MC_FALLBACK}:
            return
        if tag == qn("w:txbxContent"):
            flush()
            _walk_block(node, state, out)
            return
        if tag == qn("a:blip"):
            flush()
            _emit_image(out, state, node.get(qn("r:embed")) or node.get(qn("r:link")))
            return
        if tag == qn("w:t") and node.text:
            buf.append(node.text)
            return
        for child in node:
            walk(child)

    walk(element)
    flush()


def _walk_table(element, state: _WordDraft, out: Document) -> None:
    rows = element.findall(qn("w:tr"))
    if not rows:
        return
    parsed = [_row_cells(row) for row in rows]
    headers = [_tc_plain(cell) for cell in parsed[0]] if len(parsed) > 1 else []
    if not any(headers):
        headers = []
        body = parsed
    else:
        body = parsed[1:]
    _add_review_table(out, parsed)
    caption = state.heading
    for cells in body:
        bits: list[str] = []
        for index, cell in enumerate(cells):
            text = _tc_plain(cell)
            label = headers[index] if index < len(headers) else ""
            if text:
                bits.append(f"{label} {text}".strip() if label and label != text else text)
        line = "；".join(bits)
        if caption and line:
            line = f"{caption} {line}"
        if line:
            _emit(out, state, line)
        for cell in cells:
            _walk_cell_extra(cell, state, out)


def _add_review_table(out: Document, parsed: list[list]) -> None:
    """格子原样留在稿里，方便人工对表。导入不读这张表。"""

    width = max((len(row) for row in parsed), default=0)
    if width == 0:
        return
    table = out.add_table(rows=len(parsed), cols=width)
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    for row_index, cells in enumerate(parsed):
        for col_index, cell in enumerate(cells):
            table.rows[row_index].cells[col_index].text = _tc_plain(cell)


def _walk_cell_extra(cell, state: _WordDraft, out: Document) -> None:
    """格子里的图、文本框和嵌套表单独收，避免只剩表格时丢掉。"""

    for child in cell:
        if child.tag == qn("w:tbl"):
            _walk_table(child, state, out)
        elif child.tag == qn("w:p"):
            _walk_media(child, state, out)
        elif child.tag == qn("w:sdt"):
            _walk_block(child, state, out)


def _walk_media(element, state: _WordDraft, out: Document) -> None:
    tag = element.tag
    if tag in {qn("w:del"), qn("w:instrText"), _MC_FALLBACK}:
        return
    if tag == qn("w:txbxContent"):
        _walk_block(element, state, out)
        return
    if tag == qn("a:blip"):
        _emit_image(out, state, element.get(qn("r:embed")) or element.get(qn("r:link")))
        return
    for child in element:
        _walk_media(child, state, out)


def _row_cells(row) -> list:
    cells = []
    seen: set[int] = set()
    for cell in row.findall(qn("w:tc")):
        key = id(cell)
        if key in seen:
            continue
        seen.add(key)
        cells.append(cell)
    return cells


def _tc_plain(cell) -> str:
    parts: list[str] = []
    for child in cell:
        if child.tag == qn("w:p"):
            text = _plain_text(child)
            if text:
                parts.append(text)
    return _tidy(" ".join(parts))


def _plain_text(element) -> str:
    parts: list[str] = []

    def walk(node, in_box: bool) -> None:
        tag = node.tag
        if tag in {qn("w:del"), qn("w:instrText"), qn("w:tbl"), _MC_FALLBACK}:
            return
        if tag == qn("w:txbxContent"):
            return
        if tag == qn("w:t") and node.text and not in_box:
            parts.append(node.text)
        for child in node:
            walk(child, in_box)

    walk(element, False)
    return _tidy("".join(parts))


def _append_side_notes(src: Document, state: _WordDraft, out: Document) -> None:
    """批注和脚注放到稿子末尾。页眉页脚不收。"""

    for rel in src.part.rels.values():
        reltype = str(getattr(rel, "reltype", ""))
        if "header" in reltype or "footer" in reltype:
            continue
        if "comment" in reltype:
            label = "批注"
        elif "footnote" in reltype or "endnote" in reltype:
            label = "脚注"
        else:
            continue
        try:
            root = rel.target_part._element
        except Exception:
            continue
        for paragraph in root.iter(qn("w:p")):
            text = _plain_text(paragraph)
            if text and not _NOISE.match(text):
                _emit(out, state, f"{label} {text}")


def _emit(out: Document, state: _WordDraft, text: str) -> None:
    text = _tidy(text)
    if not text or _NOISE.match(text):
        return
    prefix = ""
    if state.heading and state.heading not in text:
        prefix = f"{state.heading} "
    room = _PARA_LIMIT - len(prefix)
    if room < 40:
        prefix = ""
        room = _PARA_LIMIT
    while text:
        piece = text[:room].strip()
        text = text[room:].strip()
        line = f"{prefix}{piece}".strip()
        if not line:
            continue
        out.add_paragraph(line)
        state.chars += len(line) + 1
        state.last = line


def _emit_image(out: Document, state: _WordDraft, rid: str | None) -> None:
    if not rid or rid in state.seen_rid:
        return
    state.seen_rid.add(rid)
    part = state.src.part.related_parts.get(rid)
    raw = getattr(part, "blob", b"") if part is not None else b""
    if not _usable_image(raw):
        return
    try:
        out.add_picture(_picture_stream(raw), width=Inches(6.0))
    except Exception:
        return
    state.figures += 1
    total = state.figure_total or state.figures
    _tell(state.on_progress, f"正在放第 {state.figures} 张图", state.figures, total)
    _add_figure_slot(out, state, state.figures)


def _picture_stream(raw: bytes):
    try:
        kind = (Image.open(io.BytesIO(raw)).format or "").upper()
        if kind in {"JPEG", "PNG", "GIF", "BMP"}:
            return io.BytesIO(raw)
    except Exception:
        pass
    return io.BytesIO(_png_bytes(raw))


def _style_val(element) -> str:
    props = element.find(qn("w:pPr"))
    if props is None:
        return ""
    style = props.find(qn("w:pStyle"))
    if style is None:
        return ""
    return style.get(qn("w:val")) or ""


def _is_heading(style: str) -> bool:
    folded = style.lower()
    return folded.startswith("heading") or "标题" in style or folded in {f"heading{i}" for i in range(1, 10)}


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _add_figure_slot(out: Document, state: _WordDraft, number: int) -> None:
    """图下留一行空图号，字由人自己填。"""

    text = f"图{number}"
    out.add_paragraph(text)
    state.chars += len(text) + 1
    state.last = text


def _word_summary(state: _WordDraft) -> str:
    text = f"已收成普通段落。图 {state.figures} 张，图上的字留空，请自己补。"
    if state.boxes:
        text += f"文本框 {state.boxes} 处已写入正文。"
    if state.chars > 20000:
        text += "正文超过约两万字，一次导入收不完，请按主题拆开再导入。"
    text += "表格留着给你对格子，下面的句子才参与切片。页眉、页脚和目录没有收。稿子开头有改稿说明。请检查后再导入。"
    return text


def _tell(on_progress, text: str, current: int, total: int) -> None:
    """有进度回调就报一步。没有也不影响出稿。"""

    if on_progress is None:
        return
    on_progress(text, current, max(total, 1))


def _count_blips(src: Document) -> int:
    """按正文里的图引用数一下，进度条用。太小的图后面仍会跳过。"""

    seen: set[str] = set()
    for node in src.element.body.iter(qn("a:blip")):
        rid = node.get(qn("r:embed")) or node.get(qn("r:link"))
        if rid:
            seen.add(rid)
    return len(seen)


def _write_guide(out: Document) -> None:
    """改稿说明放在正文最前。导入时按标记整段丢掉。"""

    for line in _GUIDE:
        out.add_paragraph(f"{_GUIDE_MARK}{line}")


def drop_draft_guide(text: str) -> str:
    """去掉出稿时写上的改稿说明，避免说明被切片。"""

    kept = [line for line in (text or "").splitlines() if not line.strip().startswith(_GUIDE_MARK)]
    return "\n".join(kept).strip()


def _already_figured(doc: Document) -> bool:
    return any(_FIGURED.match(paragraph.text.strip()) for paragraph in doc.paragraphs)


def _png_bytes(raw: bytes) -> bytes:
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _dest_path(source: Path) -> Path:
    dest = source.with_name(f"{source.stem}-图字.docx")
    number = 2
    while dest.exists():
        dest = source.with_name(f"{source.stem}-图字-{number}.docx")
        number += 1
    return dest


def _summary(total: int, more: bool) -> str:
    text = f"共 {total} 张，图上的字留空，请自己补。"
    if more:
        text += "PDF 只处理了前 40 页，后面请另存一份再出稿。"
    return text


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("用法：python -m app.kb.ready_fill 文件路径")
        return
    try:
        dest, summary = fill_figure_file(Path(sys.argv[1]))
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)
    print(f"已写成 {dest}")
    print(summary)


if __name__ == "__main__":
    main()
