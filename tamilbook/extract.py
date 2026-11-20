"""Get lines of text (with position and size) out of each PDF page.

Two sources:
  * the PDF's own text layer (fast, exact) - used when it's real Unicode Tamil
  * Tesseract OCR (for scans, or PDFs typed in legacy non-Unicode fonts)
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pymupdf

from .tamil import broken_text_score, legacy_font_score, normalize, tamil_ratio


@dataclass
class Line:
    text: str
    y0: float
    y1: float
    x0: float
    size: float              # font size (text layer) or line height (OCR)
    conf: float | None = None  # mean OCR confidence 0-100, None for text layer
    x1: float = 0.0
    low_conf_words: list[str] = field(default_factory=list)


@dataclass
class Page:
    number: int              # 1-based
    width: float
    height: float
    lines: list[Line]
    source: str              # "text" | "ocr" | "empty"
    note: str = ""


def parse_page_range(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(total))
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        start = int(a)
        end = int(b) if b else start
        out.extend(range(start - 1, min(end, total)))
    return out


def _text_layer_lines(page: pymupdf.Page) -> list[Line]:
    lines: list[Line] = []
    data = page.get_text("dict", sort=True)
    for block in data["blocks"]:
        for ln in block.get("lines", []):
            spans = ln["spans"]
            text = normalize("".join(s["text"] for s in spans))
            if not text:
                continue
            size = max(s["size"] for s in spans)
            x0, y0, x1, y1 = ln["bbox"]
            lines.append(Line(text, y0, y1, x0, size, x1=x1))
    return lines


def _ocr_lines(page: pymupdf.Page, lang: str, dpi: int, low_conf: float) -> list[Line]:
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    d = pytesseract.image_to_data(
        img, lang=lang, config="--psm 3", output_type=pytesseract.Output.DICT
    )
    scale = 72.0 / dpi  # back to PDF points so geometry matches text layer
    groups: dict[tuple, list[int]] = {}
    for i, word in enumerate(d["text"]):
        if word.strip():
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            groups.setdefault(key, []).append(i)

    lines: list[Line] = []
    for idx in groups.values():
        words = [d["text"][i] for i in idx]
        confs = [float(d["conf"][i]) for i in idx if float(d["conf"][i]) >= 0]
        top = min(d["top"][i] for i in idx)
        bottom = max(d["top"][i] + d["height"][i] for i in idx)
        left = min(d["left"][i] for i in idx)
        right = max(d["left"][i] + d["width"][i] for i in idx)
        lines.append(Line(
            text=normalize(" ".join(words)),
            y0=top * scale, y1=bottom * scale, x0=left * scale, x1=right * scale,
            size=(bottom - top) * scale,
            conf=sum(confs) / len(confs) if confs else None,
            low_conf_words=[d["text"][i] for i in idx
                            if 0 <= float(d["conf"][i]) < low_conf],
        ))
    lines.sort(key=lambda l: (round(l.y0), l.x0))
    return lines


def extract(pdf_path: str, mode: str = "auto", lang: str = "tam+eng",
            dpi: int = 300, pages: str | None = None, low_conf: float = 60,
            broken_threshold: float = 0.03,
            progress=None) -> tuple[list[Page], dict]:
    """Return (pages, pdf_metadata). mode: auto | text | ocr."""
    doc = pymupdf.open(pdf_path)
    result: list[Page] = []
    indices = parse_page_range(pages, doc.page_count)
    for n, i in enumerate(indices):
        pg = doc[i]
        w, h = pg.rect.width, pg.rect.height
        note = ""
        lines: list[Line] = []
        source = "text"
        if mode in ("auto", "text"):
            lines = _text_layer_lines(pg)
            joined = " ".join(l.text for l in lines)
            if mode == "auto":
                if len(joined) < 20:
                    note, lines = "no text layer", []
                elif legacy_font_score(joined) > 0.2 and tamil_ratio(joined) < 0.3:
                    note, lines = "legacy (non-Unicode) font detected", []
                elif broken_text_score(joined) > broken_threshold:
                    note = f"broken text layer ({broken_text_score(joined):.0%} of words corrupted)"
                    lines = []
        if mode == "ocr" or (mode == "auto" and not lines):
            lines = _ocr_lines(pg, lang, dpi, low_conf)
            source = "ocr"
        if not lines:
            source = "empty"
        result.append(Page(i + 1, w, h, lines, source, note))
        if progress:
            progress(n + 1, len(indices))
    return result, dict(doc.metadata or {})


def render_cover(pdf_path: str, dpi: int = 110) -> bytes:
    doc = pymupdf.open(pdf_path)
    return doc[0].get_pixmap(dpi=dpi).tobytes("jpeg")
