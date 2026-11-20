"""Make a small Tamil test book with the usual print furniture:
running title / author / chapter headers, page numbers, chapter openings.

  python tests/make_sample_pdf.py NotoSansTamil-Regular.ttf sample.pdf [--scanned]

--scanned also writes sample-scanned.pdf: every page as an image, no text
layer, to exercise the OCR path.
"""
import random
import sys
from pathlib import Path

import pymupdf

TITLE, AUTHOR = "ஆலமரத்து நிழல்", "கா. இளங்கோ"
SENTENCES = [
    "அந்த ஊரின் கிழக்குப் பக்கத்தில் ஒரு பெரிய ஆலமரம் இருந்தது.",
    "மாலை நேரங்களில் ஊர் மக்கள் அதன் நிழலில் அமர்ந்து பேசுவார்கள்.",
    "வள்ளி அன்று காலையிலேயே எழுந்து கிணற்றுக்குச் சென்றாள்.",
    "அவள் மனதில் ஏதோ ஒரு கவலை இருந்தது.",
    "நீ ஏன் இவ்வளவு சீக்கிரம் எழுந்தாய் என்று அம்மா கேட்டாள்.",
    "மழைக்காலம் வந்ததும் வயல்கள் எல்லாம் பச்சையாக மாறின.",
    "முருகன் தன் நண்பனோடு சந்தைக்குப் புறப்பட்டான்.",
    "வழியில் ஒரு சிறிய கோயில் இருந்தது; அங்கே விளக்கு எரிந்து கொண்டிருந்தது.",
    "பள்ளிக்கூடத்து மணி அடித்ததும் பிள்ளைகள் ஓடி வந்தனர்.",
    "ஆசிரியர் கரும்பலகையில் ஒரு புதிய பாடத்தை எழுதினார்.",
    "இரவில் வானத்தில் நட்சத்திரங்கள் மின்னிக் கொண்டிருந்தன.",
    "தாத்தா சொன்ன பழைய கதைகளை அவள் இன்னும் மறக்கவில்லை.",
]
CHAPTERS = ["காலை", "சந்தை", "மழை இரவு"]


def chapter_html(n, name, rng):
    paras = []
    for _ in range(14):
        paras.append("<p>" + " ".join(rng.choice(SENTENCES) for _ in range(rng.randint(3, 6))) + "</p>")
    return (f'<h1>அத்தியாயம் {n} — {name}</h1>' + "".join(paras))


def main(font, out, scanned=False):
    rng = random.Random(7)
    font = Path(font)
    css = (f'@font-face {{font-family: T; src: url({font.name});}} '
           'body {font-family: T; font-size: 11pt; line-height: 1.6;} '
           'h1 {font-size: 18pt; text-align: center; margin-bottom: 18pt;} '
           'p {text-indent: 18pt; margin: 0; text-align: justify;}')
    arch = pymupdf.Archive(str(font.parent))
    page_rect = pymupdf.paper_rect("a5")
    body = page_rect + (50, 60, -50, -60)
    writer_pages = []  # (chapter index, is_first_page)
    tmp = Path(out).with_suffix(".tmp.pdf")
    writer = pymupdf.DocumentWriter(str(tmp))
    for ci, name in enumerate(CHAPTERS):
        story = pymupdf.Story(chapter_html(ci + 1, name, rng), user_css=css, archive=arch)
        more, first = 1, True
        while more:
            dev = writer.begin_page(page_rect)
            more, _ = story.place(body)
            story.draw(dev)
            writer.end_page()
            writer_pages.append((ci, first))
            first = False
    writer.close()

    doc = pymupdf.open(tmp)
    hdr_css = css + " div {font-size: 9pt; text-align: center;}"
    for i, page in enumerate(doc):
        num = i + 1
        ci, first = writer_pages[i]
        if not first:  # chapter opening pages have no running header
            head = AUTHOR if num % 2 == 0 else f"{CHAPTERS[ci]}"
            if num % 4 == 1:
                head = TITLE
            page.insert_htmlbox(pymupdf.Rect(50, 25, page_rect.width - 50, 45),
                                f"<div>{head}</div>", css=hdr_css, archive=arch)
        page.insert_htmlbox(pymupdf.Rect(50, page_rect.height - 40, page_rect.width - 50,
                                         page_rect.height - 20),
                            f"<div>— {num} —</div>", css=hdr_css, archive=arch)
    doc.set_metadata({"title": "", "author": ""})
    doc.save(out)
    tmp.unlink()
    print(f"wrote {out} ({doc.page_count} pages)")

    if scanned:
        img_doc = pymupdf.open()
        for page in pymupdf.open(out):
            pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
            p = img_doc.new_page(width=page.rect.width, height=page.rect.height)
            p.insert_image(p.rect, pixmap=pix)
        sc = str(Path(out).with_name(Path(out).stem + "-scanned.pdf"))
        img_doc.save(sc)
        print(f"wrote {sc}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--scanned" in sys.argv)
