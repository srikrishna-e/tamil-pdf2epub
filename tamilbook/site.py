"""Build a free, static community library site from library/catalog.json.

Outputs index.html (search + category filter, works on phones) and opds.xml,
an OPDS catalog that e-reader apps (KOReader, Moon+ Reader, Thorium, Librera)
can add as a "network library" to browse and download books directly.
Host the output on GitHub Pages, Cloudflare Pages or Netlify - all free.
"""
from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

CATALOG = "catalog.json"


def load_catalog(library: Path) -> list[dict]:
    f = library / CATALOG
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def add_to_catalog(library: Path, entry: dict) -> None:
    books = [b for b in load_catalog(library) if b["id"] != entry["id"]]
    books.append(entry)
    books.sort(key=lambda b: (b.get("category", ""), b["title"]))
    (library / CATALOG).write_text(json.dumps(books, ensure_ascii=False, indent=2),
                                   encoding="utf-8")


def build_site(library: Path, out: Path, site_title: str, base_url: str = "") -> None:
    books = load_catalog(library)
    out.mkdir(parents=True, exist_ok=True)
    (out / "books").mkdir(exist_ok=True)
    for b in books:
        for key in ("epub", "txt"):
            if b.get(key):
                src = library / b[key]
                if src.exists():
                    shutil.copy2(src, out / "books" / src.name)
                    b[key + "_url"] = f"books/{src.name}"
    (out / "index.html").write_text(_index(books, site_title), encoding="utf-8")
    (out / "opds.xml").write_text(_opds(books, site_title, base_url), encoding="utf-8")
    (out / ".nojekyll").write_text("")


def _opds(books: list[dict], title: str, base: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = base.rstrip("/") + "/" if base else ""
    entries = []
    for b in books:
        if not b.get("epub_url"):
            continue
        entries.append(f"""<entry><title>{html.escape(b['title'])}</title>
<id>urn:tamilbook:{html.escape(b['id'])}</id><updated>{b.get('added', now)}</updated>
<author><name>{html.escape(b.get('author', ''))}</name></author>
<dc:language>ta</dc:language>
<category term="{html.escape(b.get('category', ''))}" label="{html.escape(b.get('category_ta', ''))}"/>
<link rel="http://opds-spec.org/acquisition/open-access" type="application/epub+zip" href="{base}{b['epub_url']}"/>
</entry>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/">
<id>urn:tamilbook:catalog</id><title>{html.escape(title)}</title><updated>{now}</updated>
<link rel="self" href="{base}opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<link rel="start" href="{base}opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
{''.join(entries)}
</feed>"""


def _index(books: list[dict], title: str) -> str:
    data = json.dumps(books, ensure_ascii=False).replace("</", "<\\/")
    t = html.escape(title)
    return f"""<!doctype html><html lang="ta"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t}</title><link rel="alternate" type="application/atom+xml;profile=opds-catalog" href="opds.xml">
<style>
:root{{--bg:#faf8f3;--card:#fff;--fg:#1d1b16;--mut:#6b655a;--acc:#9c3d1a;--line:#e6e0d4}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16140f;--card:#211e17;--fg:#ede6d8;--mut:#a69e8d;--acc:#f0a070;--line:#3a352b}}}}
*{{box-sizing:border-box}}body{{margin:0;font-family:"Noto Sans Tamil","Latha",system-ui,sans-serif;background:var(--bg);color:var(--fg);line-height:1.6;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}}
header,main{{max-width:960px;margin:auto;padding:1rem}}h1{{margin:.5rem 0;color:var(--acc)}}
.bar{{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}}input{{flex:1;min-width:200px;padding:.6rem;border:1px solid var(--line);border-radius:.5rem;background:var(--card);color:var(--fg);font:inherit}}
.chips{{display:flex;flex-wrap:wrap;gap:.4rem}}.chip{{border:1px solid var(--line);background:var(--card);color:var(--fg);padding:.3rem .8rem;border-radius:1rem;cursor:pointer;font:inherit}}
.chip.on{{background:var(--acc);color:var(--bg);border-color:var(--acc)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem;margin-top:1rem}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:.8rem;padding:1rem}}.card h3{{margin:0 0 .2rem}}
.meta{{color:var(--mut);font-size:.9rem}}a{{color:var(--acc)}}.dl a{{margin-right:1rem;font-weight:600}}
footer{{color:var(--mut);font-size:.85rem;text-align:center;padding:2rem 1rem}}
</style></head><body>
<header><h1>{t}</h1><div class="meta">இலவச தமிழ் மின்னூல்கள் · Free Tamil e-books · <a href="opds.xml">OPDS</a></div>
<div class="bar"><input id="q" type="search" placeholder="தேடுக… / Search title or author"></div>
<div class="chips" id="chips"></div></header>
<main><div class="grid" id="grid"></div></main>
<footer>Converted & checked by volunteers with tamilbook. Report errors on GitHub.</footer>
<script>
const BOOKS={data};
let cat="";const grid=document.getElementById("grid"),q=document.getElementById("q"),chips=document.getElementById("chips");
const cats=[...new Map(BOOKS.map(b=>[b.category,b.category_ta||b.category])).entries()];
function chip(v,l){{const c=document.createElement("button");c.className="chip"+(v===cat?" on":"");c.textContent=l;c.onclick=()=>{{cat=v;render()}};return c}}
function esc(s){{const d=document.createElement("div");d.textContent=s||"";return d.innerHTML}}
function render(){{chips.replaceChildren(chip("","அனைத்தும் · All"),...cats.map(([v,l])=>chip(v,l)));
const s=q.value.trim().toLowerCase();
grid.innerHTML=BOOKS.filter(b=>(!cat||b.category===cat)&&(!s||(b.title+" "+(b.author||"")).toLowerCase().includes(s)))
.map(b=>`<div class="card"><h3>${{esc(b.title)}}</h3><div class="meta">${{esc(b.author)}}<br>${{esc(b.category_ta)}} · ${{b.words||"?"}} சொற்கள் · QA: ${{esc(b.qa_status)}}</div>
<div class="dl">${{b.epub_url?`<a href="${{b.epub_url}}" download>EPUB</a>`:""}}${{b.txt_url?`<a href="${{b.txt_url}}" download>TXT</a>`:""}}</div></div>`).join("")||"<p>புத்தகம் இல்லை · No books found</p>"}}
q.oninput=render;render();
</script></body></html>"""
