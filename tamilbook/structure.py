"""Turn cleaned page lines into paragraphs, headings and chapters."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from .extract import Page
from .tamil import ends_sentence

CHAPTER_RE = re.compile(
    r"^(அத்தியாயம்|அதிகாரம்|பாகம்|பகுதி|படலம்|காண்டம்|chapter|part)\b"
    r"|^(அத்தியாயம்|அதிகாரம்|பாகம்|பகுதி|படலம்|காண்டம்)"   # \b is unreliable after Tamil signs
    r"|^[0-9௦-௯]{1,3}\s*[.,)]\s*\S",   # OCR often reads "5." as "5,"
    re.IGNORECASE,
)
NUMBERED_RE = re.compile(r"^[0-9௦-௯]{1,3}\s*[.,)]")
QUOTES = tuple("\"'“”‘’«»*")


@dataclass
class Block:
    kind: str                 # "h" heading | "p" paragraph | "v" verse lines
    text: str
    page: int
    generated: bool = False   # True if we invented it (not in the source)
    pages: set[int] = field(default_factory=set)


@dataclass
class Chapter:
    title: str
    blocks: list[Block]
    generated_title: bool = False


def looks_like_verse(pages: list[Page]) -> bool:
    """Poetry has many short lines relative to the page's full line length."""
    lengths = [len(l.text) for p in pages for l in p.lines]
    if len(lengths) < 20:
        return False
    full = sorted(lengths)[int(len(lengths) * 0.9)]
    short = sum(1 for n in lengths if n < 0.6 * full)
    return short / len(lengths) > 0.5


def _join(prev: str, nxt: str) -> str:
    # hyphenated line break: "exam-" + "ple" -> "example"
    if prev.endswith("-") and len(prev) > 1 and prev[-2].isalpha() \
            and nxt[:1].isalpha() and not nxt[:1].isupper():
        return prev[:-1] + nxt
    return f"{prev} {nxt}"


def build_blocks(pages: list[Page], keep_lines: bool = False) -> list[Block]:
    all_lines = [l for p in pages for l in p.lines]
    if not all_lines:
        return []
    body_size = median(l.size for l in all_lines)
    body_len = median(len(l.text) for l in all_lines)
    gaps = [b.y0 - a.y1 for p in pages for a, b in zip(p.lines, p.lines[1:])
            if b.y0 > a.y1]
    gap = median(gaps) if gaps else body_size * 0.4
    lefts = [l.x0 for l in all_lines]
    left = sorted(lefts)[len(lefts) // 5]  # robust left margin
    # Typical full line width. Headings are short and usually centred; a line
    # that spans the text block is body text even if it looks "big" (OCR line
    # height grows with quote marks and tall glyphs, so size alone misleads).
    widths = sorted(l.x1 - l.x0 for l in all_lines if l.x1 > l.x0)
    full_width = widths[int(len(widths) * 0.9)] if len(widths) >= 10 else None

    def narrow(ln) -> bool:
        return full_width is None or ln.x1 <= ln.x0 or (ln.x1 - ln.x0) < 0.75 * full_width

    # When the book numbers its chapters ("1. ...", "அத்தியாயம் 2"), trust
    # those and stop guessing headings from size after the first one: short
    # dialogue lines ("“ஆம்.”") otherwise look like big, isolated headings.
    numbered = sum(1 for l in all_lines
                   if len(l.text) <= 60 and CHAPTER_RE.match(l.text)
                   and (narrow(l) or not NUMBERED_RE.match(l.text))) >= 3
    seen_numbered = False

    blocks: list[Block] = []
    cur: Block | None = None

    def flush():
        nonlocal cur
        if cur is not None:
            blocks.append(cur)
            cur = None

    for page in pages:
        indent_px = page.width * 0.025
        for i, ln in enumerate(page.lines):
            prev = page.lines[i - 1] if i else None
            big = ln.size >= body_size * 1.25
            short = len(ln.text) <= 60
            gap_before = prev is None or (ln.y0 - prev.y1) > gap * 1.8
            # a bare number ("918) எதுவோ...") needs the narrow-heading shape;
            # a chapter word (அத்தியாயம், பாகம்) is explicit enough on its own
            chapter_line = bool(short and CHAPTER_RE.match(ln.text)
                                and (narrow(ln) or not NUMBERED_RE.match(ln.text))
                                and (big or gap_before or i == 0))
            size_heading = (short and big and gap_before and narrow(ln)
                            and not ln.text.lstrip().startswith(QUOTES)
                            and not (numbered and seen_numbered))
            is_heading = chapter_line or size_heading
            seen_numbered = seen_numbered or chapter_line
            if is_heading:
                flush()
                blocks.append(Block("h", ln.text, page.number, pages={page.number}))
                continue

            new_para = (
                cur is None
                or cur.kind == "h"
                or (prev is not None and (ln.y0 - prev.y1) > gap * 1.8)
                or (ln.x0 - left) > indent_px and not keep_lines
                or (prev is not None and ends_sentence(prev.text)
                    and len(prev.text) < 0.75 * body_len and not keep_lines)
            )
            # continuation across a page break: first line of a new page
            # continues the previous paragraph unless that one clearly ended
            if i == 0 and cur is not None and not ends_sentence(cur.text) \
                    and (ln.x0 - left) <= indent_px:
                new_para = False
            if new_para:
                flush()
                cur = Block("v" if keep_lines else "p", ln.text, page.number,
                            pages={page.number})
            else:
                cur.text = (cur.text + "\n" + ln.text) if keep_lines else _join(cur.text, ln.text)
                cur.pages.add(page.number)
    flush()
    return blocks


def make_chapters(blocks: list[Block], hints: dict[int, str] | None = None,
                  max_words: int = 6000) -> list[Chapter]:
    """Group blocks into chapters.

    Priority: detected headings > running chapter-name headers (hints) >
    fixed-size sections, so e-readers never get one giant file.
    """
    hints = hints or {}
    if not any(b.kind == "h" for b in blocks) and hints:
        out: list[Block] = []
        last = None
        for b in blocks:
            h = hints.get(b.page)
            if h and h != last:
                out.append(Block("h", h, b.page, generated=True, pages={b.page}))
                last = h
            out.append(b)
        blocks = out

    chapters: list[Chapter] = []
    cur = Chapter("தொடக்கம்", [], generated_title=True)  # "Beginning"
    for b in blocks:
        if b.kind == "h":
            if cur.blocks or not cur.generated_title:
                chapters.append(cur)
            cur = Chapter(b.text, [], generated_title=b.generated)
        else:
            cur.blocks.append(b)
    if cur.blocks or not cur.generated_title:
        chapters.append(cur)

    # split oversized chapters into parts
    final: list[Chapter] = []
    for ch in chapters:
        parts: list[list[Block]] = [[]]
        words = 0
        for b in ch.blocks:
            if words >= max_words:
                parts.append([])
                words = 0
            parts[-1].append(b)
            words += len(b.text.split())
        final.append(Chapter(ch.title, parts[0], ch.generated_title))
        for n, blk in enumerate(parts[1:], start=2):
            final.append(Chapter(f"{ch.title} — {n}", blk, generated_title=True))
    return final
