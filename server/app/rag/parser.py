"""多格式文档解析：docx/pdf/xlsx/pptx 各自使用专用 loader，禁止只做纯文本提取。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedUnit:
    """解析出的一个内容单元。location 依格式不同分别表示页码/sheet/slide。"""
    text: str
    location: str   # 例：page=3 / sheet=Sheet1 / slide=5


ALLOWED_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".pptx"}


def parse_document(file_path: Path, file_type: str) -> list[ParsedUnit]:
    """按扩展名分派到对应解析器。file_type 取值 docx/pdf/xlsx/pptx。"""
    loader = {
        "docx": _parse_docx,
        "pdf": _parse_pdf,
        "xlsx": _parse_xlsx,
        "pptx": _parse_pptx,
    }.get(file_type)
    if loader is None:
        raise ValueError(f"不支持的文件类型: {file_type}")
    return loader(file_path)


def _parse_docx(file_path: Path) -> list[ParsedUnit]:
    """Word：按段落（含标题级别信息）提取，供“标题+段落”语义切分。"""
    from docx import Document

    doc = Document(str(file_path))
    units: list[ParsedUnit] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        loc = f"heading={style}" if style.startswith("heading") else "page=1"
        units.append(ParsedUnit(text=text, location=loc))
    for ti, table in enumerate(doc.tables):
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                units.append(ParsedUnit(text=" | ".join(cells), location=f"table={ti}"))
    return units


def _parse_pdf(file_path: Path) -> list[ParsedUnit]:
    """PDF：按页提取文本（PyMuPDF），保留页码。"""
    import fitz

    doc = fitz.open(str(file_path))
    units: list[ParsedUnit] = []
    for page_no, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            units.append(ParsedUnit(text=text, location=f"page={page_no}"))
    return units


def _parse_xlsx(file_path: Path) -> list[ParsedUnit]:
    """Excel：按 sheet 拆开，每个 sheet 再按行组切分（拆分策略见 splitter）。"""
    from openpyxl import load_workbook

    wb = load_workbook(str(file_path), data_only=True)
    units: list[ParsedUnit] = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                rows.append(cells)
        text = "\n".join("\t".join(r) for r in rows)
        units.append(ParsedUnit(text=text, location=f"sheet={ws.title}"))
    return units


def _parse_pptx(file_path: Path) -> list[ParsedUnit]:
    """PPT：按 slide 提取，每个 slide 作为独立单元。"""
    from pptx import Presentation

    prs = Presentation(str(file_path))
    units: list[ParsedUnit] = []
    for idx, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        texts.append(t)
            if shape.has_table:
                for row in shape.table.rows:
                    texts.append(" | ".join(c.text.strip() for c in row.cells))
        if texts:
            units.append(ParsedUnit(text="\n".join(texts), location=f"slide={idx}"))
    return units