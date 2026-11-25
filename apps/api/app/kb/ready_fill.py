"""按一份原文件出可检查的整理稿。不入库，也不切片、不算向量。"""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

from PIL import Image
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches

from app.kb.assets import _usable_image, figures_in_document
from app.kb.ocr import ensure_ocr, read_ocr_lines

_PDF_PAGES = 40
_PARA_LIMIT = 400
_FIGURED = re.compile(r"^图\s*\d+")


def draft_bytes(file_name: str, data: bytes) -> tuple[bytes, str]:
    """根据上传内容出一份稿。原文件不改，也不写入知识库。"""

    suffix = Path(file_name or "").suffix.lower()
    if suffix not in {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
        raise ValueError("先出稿只接受 Word、PDF 或图片")
    if not data:
        raise ValueError("文件是空的")
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"source{suffix}"
        source.write_bytes(data)
        dest, summary = fill_figure_file(source)
        return dest.read_bytes(), summary


def fill_figure_file(path: Path) -> tuple[Path, str]:
    """认完写到旁边的新文件。原文件不动。返回新路径和一句结果。"""

    source = Path(path)
    if not source.is_file():
        raise ValueError("文件找不到")
    suffix = source.suffix.lower()
    ensure_ocr()
    if suffix == ".docx":
        return _fill_docx(source)
    if suffix == ".pdf":
        return _fill_pdf(source)
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
        return _fill_image(source)
    raise ValueError("只处理 Word、PDF 或图片")


def _fill_docx(source: Path) -> tuple[Path, str]:
    doc = Document(str(source))
    if _already_figured(doc):
        raise ValueError("这份里已经有图号，没有重复写。请换一份还没写过图号的文件。")
    figures = figures_in_document(doc)
    if not figures:
        dest = _dest_path(source)
        doc.save(str(dest))
        return dest, "这份没有图。稿里是原文，请按规则改成一段一件事。"
    groups: list[tuple[object, list[str]]] = []
    current_anchor = object()
    blank = 0
    for index, (anchor, raw) in enumerate(figures, start=1):
        print(f"图 {index}/{len(figures)}", flush=True)
        lines = _read_lines(raw)
        if not lines:
            blank += 1
        texts = _figure_paragraphs(index, lines)
        if anchor is current_anchor and groups:
            groups[-1][1].extend(texts)
        else:
            groups.append((anchor, texts))
            current_anchor = anchor
    for anchor, texts in groups:
        cursor = anchor
        for text in texts:
            cursor = _insert_after(doc, cursor, text)
    dest = _dest_path(source)
    doc.save(str(dest))
    return dest, _summary(len(figures), blank, False)


def _fill_pdf(source: Path) -> tuple[Path, str]:
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
        doc = Document()
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
        dest = _dest_path(source)
        doc.save(str(dest))
        note = "这份没有图。稿里是抽出的文字，请按规则改成一段一件事。"
        if more:
            note += "PDF 只处理了前 40 页，后面请另存一份再出稿。"
        return dest, note
    doc = Document()
    blank = 0
    for index, raw in enumerate(pictures, start=1):
        print(f"图 {index}/{len(pictures)}", flush=True)
        lines = _read_lines(raw)
        if not lines:
            blank += 1
        png = _png_bytes(raw)
        doc.add_picture(io.BytesIO(png), width=Inches(6.0))
        for text in _figure_paragraphs(index, lines):
            doc.add_paragraph(text)
    dest = _dest_path(source)
    doc.save(str(dest))
    return dest, _summary(len(pictures), blank, more)


def _fill_image(source: Path) -> tuple[Path, str]:
    raw = source.read_bytes()
    if not _usable_image(raw):
        raise ValueError("这张图太小，或者打不开")
    print("图 1/1", flush=True)
    lines = _read_lines(raw)
    doc = Document()
    doc.add_picture(io.BytesIO(_png_bytes(raw)), width=Inches(6.0))
    for text in _figure_paragraphs(1, lines):
        doc.add_paragraph(text)
    dest = _dest_path(source)
    doc.save(str(dest))
    blank = 0 if lines else 1
    return dest, _summary(1, blank, False)


def _already_figured(doc: Document) -> bool:
    return any(_FIGURED.match(paragraph.text.strip()) for paragraph in doc.paragraphs)


def _read_lines(raw: bytes) -> list[str]:
    try:
        return read_ocr_lines(_shrink(raw))
    except Exception:
        return []


def _shrink(raw: bytes) -> bytes:
    """认字前把大图缩小，少花时间。"""

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image.thumbnail((2000, 2800))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _png_bytes(raw: bytes) -> bytes:
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _figure_paragraphs(number: int, lines: list[str]) -> list[str]:
    """一段不超过 400 字，每段都重新写上同一个图号。"""

    prefix = f"图{number} "
    room = _PARA_LIMIT - len(prefix)
    chunks: list[str] = []
    buf = ""
    for line in lines:
        piece = " ".join(str(line).split())
        if not piece:
            continue
        while piece:
            space = room - len(buf) - (1 if buf else 0)
            if space <= 0:
                chunks.append(prefix + buf)
                buf = ""
                continue
            take = piece[:space]
            piece = piece[space:]
            buf = f"{buf} {take}".strip()
        if len(buf) >= room:
            chunks.append(prefix + buf)
            buf = ""
    if buf:
        chunks.append(prefix + buf)
    return chunks or [f"图{number} 未能读出文字"]


def _insert_after(doc: Document, anchor, text: str):
    new_p = OxmlElement("w:p")
    run = OxmlElement("w:r")
    node = OxmlElement("w:t")
    node.set(qn("xml:space"), "preserve")
    node.text = text
    run.append(node)
    new_p.append(run)
    if anchor is None:
        doc.element.body.append(new_p)
    else:
        anchor.addnext(new_p)
    return new_p


def _dest_path(source: Path) -> Path:
    dest = source.with_name(f"{source.stem}-图字.docx")
    number = 2
    while dest.exists():
        dest = source.with_name(f"{source.stem}-图字-{number}.docx")
        number += 1
    return dest


def _summary(total: int, blank: int, more: bool) -> str:
    text = f"共 {total} 张。"
    if blank:
        text += f"其中 {blank} 张没认出字。"
    if more:
        text += "PDF 只处理了前 40 页，后面请另存一份再跑。"
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
