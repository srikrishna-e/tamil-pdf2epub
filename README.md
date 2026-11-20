# tamilbook — தமிழ் PDF → மின்னூல் (EPUB / TXT)

Convert Tamil PDF books — scanned or digital — into proper e-reader formats,
with a **word-by-word quality check** so nothing is lost on the way.

பல தமிழ் நூல்கள் PDF வடிவில் மட்டுமே உள்ளன; அவை மின்னூல் கருவிகளில் (Kindle, Kobo,
KOReader) படிக்க ஏற்றவை அல்ல. இந்தக் கருவி அவற்றை EPUB ஆக மாற்றி, ஒவ்வொரு
சொல்லும் சரியாக வந்துள்ளதா என்று சரிபார்க்கிறது.

## What it does

| Step | What happens |
|---|---|
| **Extract** | Uses the PDF's text layer when it's real Unicode Tamil. Falls back to Tesseract OCR for scans, legacy fonts (Bamini, TAM, TAB…) and the very common *broken* Tamil text layer (`கிழக்Lப்`, stray `ெ`). |
| **Clean** | Removes page numbers (`12`, `— ௧௨ —`, `பக்கம் 5`, `xiv`), running headers/footers (book title, author name, chapter name) — every removal is logged. |
| **Structure** | Rejoins lines into paragraphs (also across page breaks), detects chapters (`அத்தியாயம்`, `பாகம்`, large headings, running chapter names), keeps line breaks for poetry. |
| **Categorize** | Suggests a category (நாவல், கவிதை, வரலாறு, ஆன்மீகம், சிறுவர்…) from Tamil keywords. Overridable. |
| **Write** | Valid EPUB 3 (passes epubcheck) with cover, TOC, `lang="ta"`, optional embedded Tamil font; plus TXT. |
| **QA** | Word-by-word alignment of the e-book against the PDF. Report in HTML + JSON. |
| **Publish** | Static library website + OPDS feed, hosted free on GitHub Pages. |

## Install

**Docker (easiest — everything included):**
```bash
docker build -t tamilbook .
docker run --rm -v "$PWD:/work" tamilbook convert book.pdf -o out
```

**Or locally** (Python 3.10+):
```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-tam fonts-noto-core
# macOS
brew install tesseract tesseract-lang
# Windows: install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
#          and tick "Tamil" under additional languages

pip install -e .
```

Better OCR: replace the default Tamil model with `tam.traineddata` from
[tessdata_best](https://github.com/tesseract-ocr/tessdata_best).

## Usage

```bash
# One book
tamilbook convert book.pdf -o out --title "பொன்னியின் செல்வன்" --author "கல்கி"

# Try the first 20 pages first
tamilbook convert book.pdf -o out --pages 1-20

# Poetry: keep line breaks (auto-detected, but you can force it)
tamilbook convert kavithai.pdf -o out --keep-lines yes

# Embed a Tamil font (recommended for Kobo / Kindle)
tamilbook convert book.pdf -o out --embed-font NotoSansTamil-Regular.ttf

# A whole folder into the library
tamilbook batch pdfs/ -o library
```

For `batch`, put an optional `mybook.json` next to `mybook.pdf`:
```json
{"title": "பொன்னியின் செல்வன்", "author": "கல்கி", "category": "fiction"}
```
Categories: `fiction`, `short-stories`, `poetry`, `classical`, `history`,
`biography`, `religion`, `science`, `society`, `children`, `health`, `cooking`.

Output for each book: `name.epub`, `name.txt`, `name.qa.html`, `name.qa.json`,
`name.meta.json`.

## The QA report — how "nothing is missed" is checked

1. **Accounting.** Every word read from the PDF must end up either in the
   e-book or in the removal ledger (page numbers, headers). The e-book is
   aligned word-by-word against the source; every **missing**, **extra** or
   **changed** word is listed with its page number and surrounding words.
   Status is `FAIL` if any are found.
2. **Ledger audit.** Every removed line is listed. Long removed lines (which
   probably aren't headers) are flagged.
3. **Source quality.** Words OCR wasn't confident about, impossible Tamil
   letter sequences, blank or suspiciously short pages.
4. **`--crosscheck`** (slow): OCRs pages that used the PDF text layer and
   compares, catching text layers that look fine but aren't.

**Limits, honestly:** the QA proves the conversion didn't drop, duplicate or
reorder text. It cannot know that OCR read `ஊரின்` as `களரின்` with high
confidence. Scanned books still need a human proofreading pass — the workflow
below makes that safe.

## Proofreading workflow (for volunteers)

```bash
tamilbook convert book.pdf -o out        # 1. convert
# 2. open out/book.txt in any editor, fix OCR mistakes.
#    Lines starting with "# " are chapter titles. Blank line = new paragraph.
tamilbook qa book.pdf out/book.txt       # 3. check nothing was deleted by accident
tamilbook build out/book.txt             # 4. make the final EPUB
```

`qa` reports your small corrections as *info*, but anything accidentally
deleted or pasted twice as an *error*.

## Free hosting for the community

1. Push this repo to GitHub.
2. **Settings → Pages → Source: GitHub Actions.**
3. Commit converted books into `library/` (via `tamilbook batch … -o library`).
4. The `publish library` workflow builds the site automatically:
   `https://<you>.github.io/<repo>/`

Readers can browse on any phone, or add `https://<you>.github.io/<repo>/opds.xml`
as an OPDS catalog in KOReader, Moon+ Reader, Librera or Thorium to download
straight to their e-reader.

Limits: GitHub Pages sites should stay under 1 GB, with no file over 100 MB.
Tamil EPUBs are usually 0.5–3 MB, so that's hundreds of books. For more, put
EPUBs in GitHub Releases or the Internet Archive and link them in
`catalog.json`. Cloudflare Pages and Netlify are free alternatives.

## ⚠️ Copyright

Only publish books that are in the **public domain**, **nationalised
(நாட்டுடைமை) by the Tamil Nadu government**, or that you have **permission**
for. Check each book's status before committing it to `library/`. Consider
coordinating with [Project Madurai](https://www.projectmadurai.org/) and the
[Tamil Virtual Academy](https://www.tamilvu.org/) to avoid duplicating work.

## Development

```bash
pip install -e ".[dev]"
pytest -q          # fast unit tests + an end-to-end test if tesseract-tam is installed
```

Code map: `extract.py` (text layer / OCR) → `clean.py` (furniture removal) →
`structure.py` (paragraphs, chapters) → `categorize.py` → `writers.py`
(EPUB/TXT) → `qa.py` → `site.py`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — free to use, modify and share.
