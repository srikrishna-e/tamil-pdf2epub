"""tamilbook command line.

  tamilbook convert book.pdf -o out/            PDF -> EPUB + TXT + QA report
  tamilbook batch pdfs/ -o library/             convert a folder, update catalog
  tamilbook qa book.pdf out/book.txt            check a proofread TXT against the PDF
  tamilbook build out/book.txt                  proofread TXT -> EPUB
  tamilbook site library/ -o site/              static website + OPDS feed
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .categorize import CATEGORIES, categorize
from .clean import find_furniture
from .extract import extract, render_cover
from .qa import Report, align, crosscheck_ocr, finalize, run_qa, save, source_quality, _expected_stream
from .site import add_to_catalog, build_site
from .structure import build_blocks, looks_like_verse, make_chapters
from .writers import read_text, write_epub, write_text
from .tamil import tokens


def _progress(done: int, total: int) -> None:
    print(f"\r  pages {done}/{total}", end="", file=sys.stderr, flush=True)
    if done == total:
        print(file=sys.stderr)


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\u0B80-\u0BFF-]+", "-", name).strip("-")
    return s or hashlib.sha1(name.encode()).hexdigest()[:10]


def _pipeline(args, pdf: Path):
    print(f"• Extracting {pdf.name} (mode={args.mode})", file=sys.stderr)
    pages, pdfmeta = extract(str(pdf), args.mode, args.lang, args.dpi, args.pages,
                             progress=_progress)
    raw = copy.deepcopy(pages)
    furn = find_furniture(pages, min_repeat=args.min_repeat)
    verse = {"yes": True, "no": False}.get(args.keep_lines) if args.keep_lines != "auto" \
        else looks_like_verse(pages)
    blocks = build_blocks(pages, keep_lines=verse)
    chapters = make_chapters(blocks, furn.chapter_hints)
    return pages, raw, furn, verse, chapters, pdfmeta


def convert(args, pdf: Path, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    pages, raw, furn, verse, chapters, pdfmeta = _pipeline(args, pdf)
    body = " ".join(b.text for ch in chapters for b in ch.blocks)
    cat = categorize(body, verse_hint=verse)
    if args.category:
        cat["category"] = args.category
        cat["category_ta"] = CATEGORIES.get(args.category, {}).get("ta", args.category)

    title = args.title or (pdfmeta.get("title") or "").strip() or pdf.stem
    author = args.author or (pdfmeta.get("author") or "").strip()
    stem = _slug(args.name or pdf.stem)
    meta = {
        "id": stem, "title": title, "author": author, "language": "ta",
        "source": pdf.name, "category": cat["category"], "category_ta": cat["category_ta"],
        "category_scores": cat["scores"], "verse": verse,
        "running_headers": furn.book_headers[:4],
        "generated_titles": sorted({c.title for c in chapters if c.generated_title}),
        "tool": f"tamilbook {__version__}",
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    print("• Running word-by-word QA", file=sys.stderr)
    report = run_qa(raw, pages, furn.ledger, chapters)
    if args.crosscheck:
        print("• Cross-checking text layer against OCR", file=sys.stderr)
        crosscheck_ocr(str(pdf), pages, report, args.lang, args.dpi)
        finalize(report)
    meta.update(words=report.stats["output_words"], pages=report.stats["pages"],
                qa_status=report.status)

    files = {}
    if "txt" in args.format:
        write_text(outdir / f"{stem}.txt", chapters)
        files["txt"] = f"{stem}.txt"
    if "epub" in args.format:
        cover = None if args.no_cover else render_cover(str(pdf))
        write_epub(outdir / f"{stem}.epub", chapters, meta, cover,
                   Path(args.embed_font) if args.embed_font else None)
        files["epub"] = f"{stem}.epub"
    meta.update(files)
    save(report, outdir / f"{stem}.qa.json", outdir / f"{stem}.qa.html", title)
    (outdir / f"{stem}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    s = report.stats
    print(f"✓ {title} | {cat['category_ta']} | {len(chapters)} chapters | "
          f"{s['output_words']} words | removed {s['removed_lines']} header/footer lines | "
          f"QA {report.status} ({s['accounted']} accounted, {s['missing']} missing, "
          f"{s['extra']} extra, {s['changed']} changed)")
    if furn.book_headers:
        print(f"  running headers seen: {furn.book_headers[:4]}  "
              f"(tip: use --title/--author if metadata is wrong)")
    print(f"  report: {outdir / (stem + '.qa.html')}")
    return meta


def cmd_convert(args):
    meta = convert(args, Path(args.pdf), Path(args.output))
    return 1 if args.strict and meta["qa_status"] == "FAIL" else 0


def cmd_batch(args):
    lib = Path(args.output)
    failed = 0
    default_category = args.category
    for pdf in sorted(Path(args.folder).glob("*.pdf")):
        # optional sidecar: mybook.json next to mybook.pdf
        # {"title": "...", "author": "...", "category": "..."}
        side = pdf.with_suffix(".json")
        info = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
        args.title, args.author, args.name = info.get("title"), info.get("author"), None
        args.category = info.get("category", default_category)
        try:
            meta = convert(args, pdf, lib / "books")
            meta["epub"] = f"books/{meta['epub']}" if meta.get("epub") else None
            meta["txt"] = f"books/{meta['txt']}" if meta.get("txt") else None
            add_to_catalog(lib, {k: meta.get(k) for k in (
                "id", "title", "author", "category", "category_ta", "words",
                "pages", "qa_status", "epub", "txt", "added")})
        except Exception as e:  # keep going on bad files
            failed += 1
            print(f"✗ {pdf.name}: {e}", file=sys.stderr)
    return 1 if failed else 0


def cmd_qa(args):
    """Check a (proofread) text file against the source PDF."""
    pages, _ = extract(args.pdf, args.mode, args.lang, args.dpi, args.pages, progress=_progress)
    furn = find_furniture(pages, min_repeat=args.min_repeat)
    meta_path = Path(args.txt).with_suffix(".meta.json")
    gen = set(json.loads(meta_path.read_text(encoding="utf-8")).get("generated_titles", [])) \
        if meta_path.exists() else set()
    chapters = read_text(Path(args.txt), gen)
    report = Report()
    expected, where = _expected_stream(pages)
    got = [t for ch in chapters for t in
           ((tokens(ch.title) if not ch.generated_title else []) +
            [w for b in ch.blocks for w in tokens(b.text)])]
    res = align(expected, where, got, report, proofread=True)
    source_quality(pages, report)
    report.stats = {"expected_words": len(expected), "output_words": len(got), **res}
    finalize(report)
    stem = Path(args.txt).with_suffix("")
    save(report, Path(f"{stem}.proof-qa.json"), Path(f"{stem}.proof-qa.html"), Path(args.txt).name)
    print(f"QA {report.status}: {res} → {stem}.proof-qa.html")
    return 1 if report.status == "FAIL" else 0


def cmd_build(args):
    txt = Path(args.txt)
    meta_path = txt.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() \
        else {"id": txt.stem, "title": txt.stem}
    for k in ("title", "author"):
        if getattr(args, k):
            meta[k] = getattr(args, k)
    chapters = read_text(txt, set(meta.get("generated_titles", [])))
    out = Path(args.output) if args.output else txt.with_suffix(".epub")
    write_epub(out, chapters, meta, Path(args.cover).read_bytes() if args.cover else None,
               Path(args.embed_font) if args.embed_font else None)
    print(f"✓ {out}")
    return 0


def cmd_site(args):
    build_site(Path(args.library), Path(args.output), args.title, args.base_url)
    print(f"✓ site written to {args.output}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="tamilbook", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def extraction_opts(sp):
        sp.add_argument("--mode", choices=["auto", "text", "ocr"], default="auto",
                        help="auto: use text layer, OCR when missing/legacy font")
        sp.add_argument("--lang", default="tam+eng", help="Tesseract languages")
        sp.add_argument("--dpi", type=int, default=300)
        sp.add_argument("--pages", help="e.g. 1-20,25 (for testing)")
        sp.add_argument("--min-repeat", type=int, default=3,
                        help="pages a margin line must repeat on to count as header/footer")

    def book_opts(sp):
        sp.add_argument("--format", default="epub,txt")
        sp.add_argument("--category", help="override detected category")
        sp.add_argument("--keep-lines", choices=["auto", "yes", "no"], default="auto",
                        help="keep original line breaks (poetry)")
        sp.add_argument("--embed-font", help="TTF to embed (e.g. NotoSansTamil-Regular.ttf)")
        sp.add_argument("--no-cover", action="store_true", help="don't use page 1 as cover")
        sp.add_argument("--crosscheck", action="store_true",
                        help="also OCR text-layer pages and compare (slow, thorough)")
        sp.add_argument("--strict", action="store_true", help="exit 1 if QA fails")

    c = sub.add_parser("convert", help="convert one PDF")
    c.add_argument("pdf")
    c.add_argument("-o", "--output", default="out")
    c.add_argument("--title")
    c.add_argument("--author")
    c.add_argument("--name", help="output file name (default: PDF name)")
    extraction_opts(c)
    book_opts(c)
    c.set_defaults(func=cmd_convert)

    b = sub.add_parser("batch", help="convert every PDF in a folder into a library")
    b.add_argument("folder")
    b.add_argument("-o", "--output", default="library")
    extraction_opts(b)
    book_opts(b)
    b.set_defaults(func=cmd_batch)

    q = sub.add_parser("qa", help="check a proofread .txt against the PDF")
    q.add_argument("pdf")
    q.add_argument("txt")
    extraction_opts(q)
    q.set_defaults(func=cmd_qa)

    bd = sub.add_parser("build", help="turn a proofread .txt into EPUB")
    bd.add_argument("txt")
    bd.add_argument("-o", "--output")
    bd.add_argument("--title")
    bd.add_argument("--author")
    bd.add_argument("--cover", help="cover image (jpg)")
    bd.add_argument("--embed-font")
    bd.set_defaults(func=cmd_build)

    s = sub.add_parser("site", help="build the static library website + OPDS feed")
    s.add_argument("library")
    s.add_argument("-o", "--output", default="site")
    s.add_argument("--title", default="தமிழ் மின்னூலகம்")
    s.add_argument("--base-url", default="", help="public URL, for the OPDS feed")
    s.set_defaults(func=cmd_site)

    args = p.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
