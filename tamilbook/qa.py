"""Word-by-word quality check.

Three layers:

1. ACCOUNTING  every word extracted from the PDF must end up either in the
   e-book or in the removal ledger (page numbers / running headers). The
   e-book is aligned word-by-word against "source minus ledger"; any word
   that is missing, extra or changed is reported with its page number.
   Words split by a line-break hyphen ("exam-" + "ple") count as matches.

2. LEDGER AUDIT  everything we removed is listed, and anything that doesn't
   look like furniture (long lines, sentences) is flagged for review.

3. SOURCE QUALITY  things a word diff can't see: OCR low-confidence words,
   broken Tamil letter sequences, pages with suspiciously little text, and
   (optional) a cross-check of the PDF text layer against fresh OCR.
"""
from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median

from .clean import Removed
from .extract import Page
from .structure import Chapter
from .tamil import has_invalid_sequence, tokens


@dataclass
class Issue:
    severity: str        # "error" | "warning" | "info"
    kind: str
    page: int | None
    detail: str
    expected: str = ""
    got: str = ""


@dataclass
class Report:
    status: str = "PASS"
    stats: dict = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    ledger: list[dict] = field(default_factory=list)

    def add(self, *a, **kw):
        self.issues.append(Issue(*a, **kw))


def _expected_stream(pages: list[Page]) -> tuple[list[str], list[int]]:
    words, where = [], []
    for p in pages:
        for ln in p.lines:
            for t in tokens(ln.text):
                words.append(t)
                where.append(p.number)
    return words, where


def output_stream(chapters: list[Chapter]) -> list[str]:
    out: list[str] = []
    for ch in chapters:
        if not ch.generated_title:
            out.extend(tokens(ch.title))
        for b in ch.blocks:
            if not b.generated:
                out.extend(tokens(b.text))
    return out


def _ctx(words: list[str], i: int, j: int, pad: int = 4) -> str:
    left = " ".join(words[max(0, i - pad):i])
    mid = " ".join(words[i:j])
    right = " ".join(words[j:j + pad])
    return f"…{left} [{mid}] {right}…"


def align(expected: list[str], where: list[int], got: list[str], report: Report,
          max_issues: int = 500, proofread: bool = False) -> dict:
    """proofread=True: small word substitutions are expected (they are the
    proofreader's corrections) and are reported as info, not errors."""
    sm = SequenceMatcher(None, expected, got, autojunk=False)
    matched = joined = missing = extra = changed = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            matched += i2 - i1
            continue
        if op == "replace" and "".join(expected[i1:i2]) == "".join(got[j1:j2]):
            joined += i2 - i1          # same letters, different spacing/hyphen
            continue
        page = where[i1] if i1 < len(where) else (where[-1] if where else None)
        if op == "delete":
            missing += i2 - i1
            kind, sev = "missing-words", "error"
        elif op == "insert":
            extra += j2 - j1
            kind, sev = "extra-words", "error"
        else:
            changed += max(i2 - i1, j2 - j1)
            small = max(i2 - i1, j2 - j1) <= 3
            kind = "correction" if proofread and small else "changed-words"
            sev = "info" if proofread and small else "error"
        if len(report.issues) < max_issues:
            report.add(sev, kind, page, f"{i2 - i1} source word(s) vs {j2 - j1} output word(s)",
                       expected=_ctx(expected, i1, i2), got=_ctx(got, j1, j2))
    return {"matched": matched, "joined": joined, "missing": missing,
            "extra": extra, "changed": changed}


def audit_ledger(ledger: list[Removed], report: Report) -> None:
    for r in ledger:
        report.ledger.append(asdict(r))
        if len(r.text) > 70 or (len(tokens(r.text)) > 8):
            report.add("warning", "suspicious-removal", r.page,
                       f"Removed a long {r.reason} line - check it really is a header/footer",
                       expected=r.text)


def source_quality(pages: list[Page], report: Report) -> None:
    counts = [len(tokens(" ".join(l.text for l in p.lines))) for p in pages]
    typical = median(counts) if counts else 0
    for p, n in zip(pages, counts):
        if p.note:
            report.add("info", "extraction", p.number, f"Used OCR: {p.note}")
        if p.source == "empty":
            report.add("warning", "empty-page", p.number,
                       "No text found (blank page or image only?)")
        elif typical > 30 and n < typical * 0.25:
            report.add("warning", "sparse-page", p.number,
                       f"Only {n} words (typical page: {int(typical)}). Picture, or missed text?")
        bad = [w for l in p.lines for w in l.text.split() if has_invalid_sequence(w)]
        if bad:
            report.add("warning", "broken-tamil", p.number,
                       f"{len(bad)} word(s) with impossible Tamil letter sequences",
                       got=" ".join(bad[:15]))
        low = [w for l in p.lines for w in l.low_conf_words]
        if low:
            report.add("warning" if len(low) > 10 else "info", "low-ocr-confidence",
                       p.number, f"{len(low)} word(s) OCR wasn't sure about",
                       got=" ".join(low[:20]))


def crosscheck_ocr(pdf_path: str, pages: list[Page], report: Report, lang: str,
                   dpi: int, threshold: float = 0.85) -> None:
    """Independent check: OCR text-layer pages and compare. Catches legacy-font
    garbage that still 'looks' Tamil, hidden text, and missing glyphs."""
    import pymupdf
    from .extract import _ocr_lines
    doc = pymupdf.open(pdf_path)
    for p in pages:
        if p.source != "text":
            continue
        ocr = tokens(" ".join(l.text for l in _ocr_lines(doc[p.number - 1], lang, dpi, 0)))
        txt = tokens(" ".join(l.text for l in p.lines))
        ratio = SequenceMatcher(None, txt, ocr, autojunk=False).ratio() if txt or ocr else 1
        if ratio < threshold:
            report.add("warning", "text-layer-mismatch", p.number,
                       f"PDF text layer and OCR agree on only {ratio:.0%} of words")


def run_qa(raw_pages: list[Page], cleaned_pages: list[Page], ledger: list[Removed],
           chapters: list[Chapter]) -> Report:
    report = Report()
    raw_words = sum(len(tokens(l.text)) for p in raw_pages for l in p.lines)
    removed_words = sum(len(tokens(r.text)) for r in ledger)
    expected, where = _expected_stream(cleaned_pages)
    got = output_stream(chapters)
    res = align(expected, where, got, report)
    audit_ledger(ledger, report)
    source_quality(cleaned_pages, report)
    report.stats = {
        "pages": len(raw_pages),
        "pages_ocr": sum(p.source == "ocr" for p in raw_pages),
        "source_words": raw_words,
        "removed_words": removed_words,
        "removed_lines": len(ledger),
        "expected_words": len(expected),
        "output_words": len(got),
        **res,
        "accounted": f"{(res['matched'] + res['joined']) / max(len(expected), 1):.4%}",
    }
    if raw_words != len(expected) + removed_words:
        report.add("error", "accounting", None,
                   f"source {raw_words} ≠ kept {len(expected)} + removed {removed_words}")
    finalize(report)
    return report


def finalize(report: Report) -> None:
    sev = {i.severity for i in report.issues}
    report.status = "FAIL" if "error" in sev else "WARN" if "warning" in sev else "PASS"


def save(report: Report, json_path: Path, html_path: Path, title: str) -> None:
    data = asdict(report)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_html(data, title), encoding="utf-8")


def _html(d: dict, title: str) -> str:
    color = {"PASS": "#1a7f37", "WARN": "#9a6700", "FAIL": "#cf222e"}[d["status"]]
    stats = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
                    for k, v in d["stats"].items())
    rows = "".join(
        f'<tr class="{i["severity"]}"><td>{i["severity"]}</td><td>{html.escape(i["kind"])}</td>'
        f'<td>{i["page"] or ""}</td><td>{html.escape(i["detail"])}'
        + (f'<div class="exp">PDF: {html.escape(i["expected"])}</div>' if i["expected"] else "")
        + (f'<div class="got">Book: {html.escape(i["got"])}</div>' if i["got"] else "")
        + "</td></tr>" for i in d["issues"])
    ledger = "".join(f'<tr><td>{r["page"]}</td><td>{html.escape(r["reason"])}</td>'
                     f'<td>{html.escape(r["text"])}</td></tr>' for r in d["ledger"])
    return f"""<!doctype html><html lang="ta"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA – {html.escape(title)}</title><style>
:root{{--bg:#fff;--fg:#1f2328;--mut:#656d76;--line:#d0d7de;--err:#ffebe9;--warn:#fff8c5}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--mut:#8d96a0;--line:#30363d;--err:#3c1618;--warn:#3a2e05}}}}
body{{font-family:"Noto Sans Tamil",system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1100px;margin:auto;padding:1rem}}
.badge{{display:inline-block;padding:.2em .8em;border-radius:1em;color:#fff;background:{color};font-weight:700}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}td,th{{border-bottom:1px solid var(--line);padding:.4rem;text-align:left;vertical-align:top}}
tr.error{{background:var(--err)}}tr.warning{{background:var(--warn)}}.exp,.got{{font-size:.9em;color:var(--mut);margin-top:.3em}}
details{{margin:1rem 0}}.wrap{{overflow-x:auto}}</style></head><body>
<h1>{html.escape(title)} <span class="badge">{d["status"]}</span></h1>
<div class="wrap"><table>{stats}</table></div>
<h2>Issues ({len(d["issues"])})</h2>
<div class="wrap"><table><tr><th>Severity</th><th>Type</th><th>Page</th><th>Detail</th></tr>{rows}</table></div>
<details><summary>Removed lines ({len(d["ledger"])}) – page numbers, headers, footers</summary>
<div class="wrap"><table><tr><th>Page</th><th>Reason</th><th>Text</th></tr>{ledger}</table></div></details>
</body></html>"""
