"""Remove page "furniture": page numbers and running headers/footers.

Idea: real body text almost never repeats in the top/bottom lines of many
pages, but the book title, author name, chapter name and page number do.
So we collect lines from each page's margin zone, normalise them (digits ->
'#', so "12 - கல்கி" and "13 - கல்கி" match), cluster near-duplicates (OCR is
noisy), and drop anything that repeats on enough pages.

Every removed line goes into a ledger so the QA step can prove that the only
words missing from the e-book are exactly the ones we meant to remove.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import median

from .extract import Page
from .structure import CHAPTER_RE
from .tamil import DIGITS_RE, WORD_RE, normalize

_ROMAN = r"(?=[mdclxvi])m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
PAGE_NUM_RE = re.compile(
    rf"^\W*(?:(?:page|pg|p|பக்கம்|பக்)\.?\s*)?(?:[0-9௦-௯]{{1,4}}|{_ROMAN})\W*$",
    re.IGNORECASE,
)


@dataclass
class Removed:
    page: int
    text: str
    reason: str          # "page-number" | "running-header" | "running-footer" |
                         # "illustration-noise" | "repeated-chapter-title"
    cluster: int | None = None


@dataclass
class Furniture:
    ledger: list[Removed]
    book_headers: list[str]          # repeat across much of the book (title/author)
    chapter_hints: dict[int, str]    # page -> running chapter title on that page


def _key(text: str) -> str:
    t = DIGITS_RE.sub("#", normalize(text).lower())
    t = re.sub(r"[^\w\u0B80-\u0BFF#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _margin_indices(page: Page, k: int, zone: float) -> list[tuple[int, str]]:
    """Indices of lines in the top/bottom margin zone, tagged 'top'/'bottom'."""
    n = len(page.lines)
    out = []
    for i, ln in enumerate(page.lines):
        if i < k and ln.y0 < page.height * zone:
            out.append((i, "top"))
        elif i >= n - k and ln.y1 > page.height * (1 - zone):
            out.append((i, "bottom"))
    return out


def find_furniture(pages: list[Page], min_repeat: int = 3, k: int = 2,
                   zone: float = 0.15, fuzz: float = 0.85) -> Furniture:
    # 1. cluster margin lines by fuzzy key
    reps: list[str] = []                  # representative key per cluster
    members: list[set[int]] = []          # pages per cluster
    texts: list[str] = []                 # first original text per cluster
    assign: dict[tuple[int, int], int] = {}

    for p_idx, page in enumerate(pages):
        for i, _pos in _margin_indices(page, k, zone):
            text = page.lines[i].text
            key = _key(text)
            if not WORD_RE.search(key.replace("#", "")):
                continue  # pure numbers handled separately
            cid = None
            for c, rep in enumerate(reps):
                sm = SequenceMatcher(None, key, rep, autojunk=False)
                if sm.real_quick_ratio() >= fuzz and sm.quick_ratio() >= fuzz \
                        and sm.ratio() >= fuzz:
                    cid = c
                    break
            if cid is None:
                cid = len(reps)
                reps.append(key)
                members.append(set())
                texts.append(text)
            members[cid].add(page.number)
            assign[(p_idx, i)] = cid

    repeating = {c for c, pg in enumerate(members) if len(pg) >= min_repeat}
    n_pages = max(len(pages), 1)
    book_level = {c for c in repeating if len(members[c]) >= 0.3 * n_pages}

    # A chapter title printed big on the chapter's first page is a real
    # heading, not furniture, even though it matches the running header.
    sizes: dict[int, list[float]] = {}
    for (p_idx, i), cid in assign.items():
        sizes.setdefault(cid, []).append(pages[p_idx].lines[i].size)
    keep: set[tuple[int, int]] = set()
    for (p_idx, i), cid in assign.items():
        if cid in repeating and cid not in book_level:
            s = sorted(sizes[cid])
            if pages[p_idx].lines[i].size >= 1.15 * s[len(s) // 2]:
                keep.add((p_idx, i))

    # Body statistics for the "isolated line" rule below
    all_lines = [l for p in pages for l in p.lines]
    body_size = median(l.size for l in all_lines) if all_lines else 0
    gaps = [b.y0 - a.y1 for p in pages for a, b in zip(p.lines, p.lines[1:]) if b.y0 > a.y1]
    body_gap = median(gaps) if gaps else 0

    def isolated(page: Page, i: int, pos: str) -> bool:
        """Short, centred line cut off from the body by a big gap: a header or
        footer even if it appears only once (e.g. a 2-page chapter's name)."""
        ln = page.lines[i]
        j = i + 1 if pos == "top" else i - 1
        if not (0 <= j < len(page.lines)) or not ln.x1 or not body_gap:
            return False
        nb = page.lines[j]
        gap = nb.y0 - ln.y1 if pos == "top" else ln.y0 - nb.y1
        centre = (ln.x0 + ln.x1) / 2
        return (len(ln.text) <= 60 and len(ln.text.split()) <= 8
                and ln.size < body_size * 1.25 and not CHAPTER_RE.match(ln.text)
                and gap > body_gap * 2.5
                and abs(centre - page.width / 2) < page.width * 0.08
                and (ln.x1 - ln.x0) < page.width * 0.6)

    # 2. build the ledger and strip lines
    ledger: list[Removed] = []
    hints: dict[int, str] = {}
    for p_idx, page in enumerate(pages):
        drop: dict[int, Removed] = {}
        n = len(page.lines)
        margin = dict(_margin_indices(page, k, zone))
        # walk from the page edge inwards; stop at the first real body line
        for order in (range(min(k, n)), range(n - 1, max(n - k, 0) - 1, -1)):
            for i in order:
                pos = margin.get(i)
                if pos is None or i in drop:
                    break
                text = page.lines[i].text
                if PAGE_NUM_RE.match(text):
                    drop[i] = Removed(page.number, text, "page-number")
                elif assign.get((p_idx, i)) in repeating and (p_idx, i) not in keep:
                    cid = assign[(p_idx, i)]
                    drop[i] = Removed(page.number, text,
                                      f"running-{'header' if pos == 'top' else 'footer'}", cid)
                    if cid not in book_level:
                        clean = DIGITS_RE.sub("", text).strip(" -–—|.:")
                        if clean:
                            hints[page.number] = normalize(clean)
                elif isolated(page, i, pos):
                    drop[i] = Removed(page.number, text,
                                      f"isolated-{'header' if pos == 'top' else 'footer'}")
                else:
                    break
        ledger.extend(drop[i] for i in sorted(drop))
        page.lines = [ln for i, ln in enumerate(page.lines) if i not in drop]

    ledger.extend(_strip_illustration_noise(pages))
    ledger.extend(_strip_repeated_chapter_titles(pages))
    ledger.sort(key=lambda r: r.page)

    book_headers = [texts[c] for c in sorted(book_level, key=lambda c: -len(members[c]))]
    return Furniture(ledger, book_headers, hints)


def _strip_illustration_noise(pages: list[Page], noise_conf: float = 60) -> list[Removed]:
    """Drop OCR garbage read out of pictures ("(Nasal", "eit sip sip").

    Only on illustration pages - OCR pages with very few lines, or whose
    typical line confidence is low. Short dialogue lines ("ஆம்.") also get
    low confidence, so this is never applied to ordinary text pages. Lines
    OCR is confident about (a caption) are kept.
    """
    counts = [len(p.lines) for p in pages if p.source == "ocr" and p.lines]
    if not counts:
        return []
    typical = median(counts)
    out: list[Removed] = []
    for page in pages:
        if page.source != "ocr" or not page.lines:
            continue
        confs = [ln.conf if ln.conf is not None else 100 for ln in page.lines]
        if not (len(page.lines) < 0.4 * typical or median(confs) < noise_conf):
            continue
        keep = []
        for ln, c in zip(page.lines, confs):
            if c < noise_conf:
                out.append(Removed(page.number, ln.text, "illustration-noise"))
            else:
                keep.append(ln)
        page.lines = keep
    return out


def _title_part(text: str) -> str:
    return re.sub(r"^[0-9௦-௯]{1,3}\s*[.,)]\s*", "", text).strip()


def _strip_repeated_chapter_titles(pages: list[Page], fuzz: float = 0.9) -> list[Removed]:
    """Drop a chapter title repeated later, e.g. as a caption under an
    illustration ("27. சுமை தாங்கி" on the chapter page and again on a picture)."""
    seen: list[str] = []
    out: list[Removed] = []
    for page in pages:
        keep = []
        for ln in page.lines:
            title = _title_part(ln.text) if CHAPTER_RE.match(ln.text) else ""
            if title and any(SequenceMatcher(None, title, s).ratio() >= fuzz for s in seen[-3:]):
                out.append(Removed(page.number, ln.text, "repeated-chapter-title"))
                continue
            if title:
                seen.append(title)
            keep.append(ln)
        page.lines = keep
    return out
