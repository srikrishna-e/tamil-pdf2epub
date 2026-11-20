"""Write EPUB 3 and plain text; read proofread text back in."""
from __future__ import annotations

import html
import uuid
from pathlib import Path

from ebooklib import epub

from .structure import Block, Chapter

FONT_FACE = '@font-face { font-family: "BookTamil"; src: url("../fonts/book.ttf"); }\n'
CSS = """
body { font-family: "BookTamil", "Noto Sans Tamil", "Latha", "Vijaya", sans-serif;
       line-height: 1.7; margin: 0 4%; }
h1, h2 { text-align: center; line-height: 1.4; margin: 1.5em 0 1em; }
p { text-indent: 1.5em; margin: 0 0 0.4em; text-align: justify; }
p.verse { text-indent: 0; text-align: left; margin: 0 0 1em 1em; }
.title-page { text-align: center; margin-top: 30%; }
.title-page .author { font-size: 1.2em; margin-top: 2em; }
"""


def _chapter_html(ch: Chapter) -> str:
    parts = [f"<h2>{html.escape(ch.title)}</h2>"]
    for b in ch.blocks:
        if b.kind == "v":
            lines = "<br/>".join(html.escape(x) for x in b.text.split("\n"))
            parts.append(f'<p class="verse">{lines}</p>')
        else:
            parts.append(f"<p>{html.escape(b.text)}</p>")
    return "\n".join(parts)


def write_epub(path: Path, chapters: list[Chapter], meta: dict,
               cover: bytes | None = None, font: Path | None = None) -> None:
    book = epub.EpubBook()
    book.set_identifier(meta.get("id") or f"urn:uuid:{uuid.uuid4()}")
    book.set_title(meta["title"])
    book.set_language(meta.get("language", "ta"))
    if meta.get("author"):
        book.add_author(meta["author"])
    if meta.get("category_ta"):
        book.add_metadata("DC", "subject", meta["category_ta"])
    book.add_metadata("DC", "source", meta.get("source", ""))
    cover_page = None
    if cover:
        book.set_cover("cover.jpg", cover, create_page=False)
        cover_page = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang="ta")
        cover_page.content = ('<div style="text-align:center"><img src="cover.jpg" '
                              'alt="cover" style="max-width:100%;max-height:100%"/></div>')
        book.add_item(cover_page)

    css = epub.EpubItem(uid="style", file_name="style/book.css",
                        media_type="text/css", content=(FONT_FACE if font else "") + CSS)
    book.add_item(css)
    if font:
        book.add_item(epub.EpubItem(uid="font", file_name="fonts/book.ttf",
                                    media_type="font/ttf", content=font.read_bytes()))

    title_page = epub.EpubHtml(title=meta["title"], file_name="title.xhtml", lang="ta")
    title_page.content = (
        f'<div class="title-page"><h1>{html.escape(meta["title"])}</h1>'
        f'<div class="author">{html.escape(meta.get("author", ""))}</div></div>')
    title_page.add_item(css)
    book.add_item(title_page)

    items = []
    for i, ch in enumerate(chapters, 1):
        item = epub.EpubHtml(title=ch.title, file_name=f"chap_{i:03d}.xhtml", lang="ta")
        item.content = _chapter_html(ch)
        item.add_item(css)
        book.add_item(item)
        items.append(item)

    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ([cover_page] if cover_page else []) + [title_page, "nav", *items]
    epub.write_epub(str(path), book)


def write_text(path: Path, chapters: list[Chapter]) -> None:
    """Plain text. Headings start with '# ' so the file can be proofread and
    turned back into an EPUB with `tamilbook build`."""
    out = []
    for ch in chapters:
        out.append(f"# {ch.title}\n")
        for b in ch.blocks:
            out.append(b.text + "\n")
    path.write_text("\n".join(out), encoding="utf-8")


def read_text(path: Path, generated_titles: set[str] = frozenset()) -> list[Chapter]:
    chapters: list[Chapter] = []
    cur: Chapter | None = None
    for para in path.read_text(encoding="utf-8").split("\n\n"):
        para = para.strip("\n")
        if not para.strip():
            continue
        if para.startswith("# "):
            title = para[2:].strip()
            cur = Chapter(title, [], generated_title=title in generated_titles)
            chapters.append(cur)
            continue
        if cur is None:
            cur = Chapter("தொடக்கம்", [], generated_title=True)
            chapters.append(cur)
        kind = "v" if "\n" in para else "p"
        cur.blocks.append(Block(kind, para, 0))
    return chapters
