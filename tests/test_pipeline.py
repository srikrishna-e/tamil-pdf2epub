"""Fast tests on synthetic pages - no PDF, Tesseract or fonts needed."""
import copy

from tamilbook.categorize import categorize
from tamilbook.clean import PAGE_NUM_RE, find_furniture
from tamilbook.extract import Line, Page
from tamilbook.qa import run_qa
from tamilbook.structure import build_blocks, make_chapters
from tamilbook.tamil import broken_text_score, has_invalid_sequence, normalize, tokens

BODY = "அந்த ஊரின் கிழக்குப் பக்கத்தில் ஒரு பெரிய ஆலமரம் இருந்தது"
WORDS = ("மழை வயல் கோயில் விளக்கு சந்தை நண்பன் பள்ளி மணி ஆசிரியர் பாடம் "
         "இரவு வானம் நட்சத்திரம் தாத்தா கதை கிணறு காலை அம்மா").split()


def make_book(n=10, header=True):
    pages = []
    for num in range(1, n + 1):
        lines = []
        if header:
            text = "கா. இளங்கோ" if num % 2 == 0 else "ஆலமரத்து நிழல்"
            lines.append(Line(text, 25, 35, 170, 9, x1=250))
        y = 60
        for k in range(20):
            w = " ".join(WORDS[(num * 7 + k * 3 + j) % len(WORDS)] for j in range(6))
            lines.append(Line(f"{w} {BODY[:20]}", y, y + 12, 50, 11, x1=370))
            y += 17
        lines.append(Line(f"— {num} —", 560, 570, 200, 9, x1=220))
        pages.append(Page(num, 420, 595, lines, "text"))
    return pages


def test_normalize_strips_zwnj_after_pulli():
    assert normalize("சென்றாள்\u200c") == "சென்றாள்"


def test_tokens_keep_vowel_signs():
    assert tokens("கொண்டிருந்தது, ஊர்!") == ["கொண்டிருந்தது", "ஊர்"]


def test_invalid_sequence():
    assert has_invalid_sequence("ெக")       # vowel sign with no consonant
    assert not has_invalid_sequence("கெ")


def test_broken_text_layer_detected():
    assert broken_text_score("அந்த ஊரின் கிழக்Lப் ஒ ெ ரிய இந்த»") > 0.2
    assert broken_text_score(BODY) == 0


def test_page_number_patterns():
    for s in ["12", "— 12 —", "- ௧௨ -", "பக்கம் 5", "Page 7", "xiv"]:
        assert PAGE_NUM_RE.match(s), s
    assert not PAGE_NUM_RE.match("12 மணி")


def test_headers_and_page_numbers_removed_and_qa_passes():
    pages = make_book()
    raw = copy.deepcopy(pages)
    furn = find_furniture(pages)
    reasons = {r.reason for r in furn.ledger}
    assert "page-number" in reasons and "running-header" in reasons
    assert len(furn.ledger) == 20                      # 10 headers + 10 numbers
    text = " ".join(l.text for p in pages for l in p.lines)
    assert "இளங்கோ" not in text and "—" not in text
    chapters = make_chapters(build_blocks(pages), furn.chapter_hints)
    report = run_qa(raw, pages, furn.ledger, chapters)
    assert report.status in ("PASS", "WARN")
    assert report.stats["missing"] == 0 and report.stats["extra"] == 0


def test_qa_catches_dropped_paragraph():
    pages = make_book()
    raw = copy.deepcopy(pages)
    furn = find_furniture(pages)
    chapters = make_chapters(build_blocks(pages), furn.chapter_hints)
    b = chapters[0].blocks[0]                          # simulate a bug that
    words = b.text.split()                             # loses 15 words mid-book
    b.text = " ".join(words[:100] + words[115:])
    report = run_qa(raw, pages, furn.ledger, chapters)
    assert report.status == "FAIL"
    assert report.stats["missing"] > 0


def test_paragraph_continues_across_page_break():
    pages = make_book(2, header=False)
    for p in pages:
        p.lines = p.lines[:-1]                         # drop page numbers
    blocks = build_blocks(pages)
    assert len(blocks) == 1 and blocks[0].pages == {1, 2}


def test_categorize_religion():
    text = "இறைவன் அருள் கோயில் வழிபாடு பக்தி தேவாரம் " * 20
    assert categorize(text)["category"] == "religion"


def test_normalize_fixes_prebase_vowel_in_visual_order():
    # OCR output "தந்ைத" (ை typed before த) -> "தந்தை"
    assert normalize("தந்ைத") == "தந்தை"
    # ெ before க plus ா -> கொ
    assert normalize("ெகா") == "கொ"
    # valid text is left alone
    for word in ("தந்தை", "கொண்டு", "பெயர்", "சேவை"):
        assert normalize(word) == word


def test_big_full_width_line_is_not_a_heading():
    # OCR gives taller boxes to lines with quotes/tall glyphs; a big line that
    # spans the text block is still body text.
    pages = make_book(3, header=False)
    body = pages[1].lines
    body[5].y0 += 30
    body[5].y1 += 40
    body[5].size = 20
    for ln in body[6:]:
        ln.y0 += 40
        ln.y1 += 40
    # a short, centred, big line after a gap is a real heading
    pages[2].lines.insert(0, Line("இரண்டாம் பகுதி", 30, 50, 150, 20, x1=270))
    blocks = build_blocks(pages)
    heads = [b.text for b in blocks if b.kind == "h"]
    assert heads == ["இரண்டாம் பகுதி"]


def test_low_res_pass_recovers_missed_heading_and_chapter_number():
    from tamilbook.extract import _merge_recovered
    main = [Line("தாமரை மது", 190, 220, 265, 30, conf=61, x1=485),
            Line(BODY, 268, 295, 73, 27, conf=88, x1=709),
            Line(BODY, 400, 430, 73, 27, conf=88, x1=709)]
    low = [Line("9. தாமரை மது", 188, 222, 240, 34, conf=80, x1=485),   # adds number
           Line("18. தரிசனம்", 330, 360, 250, 30, conf=82, x1=480),    # missed line
           Line("ஒரு வேறு வாசகம் இங்கே", 268, 295, 73, 27, conf=90, x1=709),  # body: ignored
           Line("ட வ", 600, 620, 300, 20, conf=40, x1=330)]           # low conf: ignored
    lines, fixed = _merge_recovered(main, low)
    assert fixed == 2
    assert [l.text for l in lines] == ["9. தாமரை மது", BODY, "18. தரிசனம்", BODY]


def _ocr_book():
    pages = make_book(6, header=False)
    for p in pages:
        p.source = "ocr"
        for ln in p.lines:
            ln.conf = 90
    return pages


def test_illustration_noise_removed_and_ledgered():
    pages = _ocr_book()
    pic = Page(7, 420, 595, [Line("(Nasal", 100, 140, 60, 40, conf=0, x1=120),
                             Line("eit sip sip pit", 200, 220, 80, 20, conf=50, x1=300),
                             Line("27. சுமை தாங்கி", 500, 515, 150, 15, conf=95, x1=270)],
               "ocr")
    pages.append(pic)
    furn = find_furniture(pages)
    noise = [r.text for r in furn.ledger if r.reason == "illustration-noise"]
    assert noise == ["(Nasal", "eit sip sip pit"]
    assert [l.text for l in pic.lines] == ["27. சுமை தாங்கி"]   # confident caption kept
    # ordinary text pages are untouched even with low-confidence dialogue lines
    pages[2].lines[3].conf = 10
    assert all(r.page == 7 for r in furn.ledger if r.reason == "illustration-noise")


def test_repeated_chapter_title_caption_removed():
    pages = _ocr_book()
    pages[0].lines.insert(0, Line("27. சுமை தாங்கி", 30, 50, 150, 20, conf=95, x1=270))
    pages[3].lines.append(Line("27. சுமை தாங்கி", 575, 590, 150, 15, conf=95, x1=270))
    pages[4].lines.insert(0, Line("28. சுமை தூக்கி", 30, 50, 150, 20, conf=95, x1=270))
    furn = find_furniture(pages)
    reps = [(r.page, r.text) for r in furn.ledger if r.reason == "repeated-chapter-title"]
    assert reps == [(4, "27. சுமை தாங்கி")]     # the next chapter is kept


def test_numbered_book_ignores_big_dialogue_lines():
    pages = make_book(4, header=False)
    for n, p in enumerate(pages, start=1):
        p.lines.insert(0, Line(f"{n}, அத்தியாயத் தலைப்பு", 20, 40, 150, 14, x1=270))
    d = pages[2].lines
    d[5] = Line("“ஆம்.”", d[5].y0 + 30, d[5].y1 + 36, 50, 20, x1=110)
    heads = [b.text for b in build_blocks(pages) if b.kind == "h"]
    assert heads == [f"{n}, அத்தியாயத் தலைப்பு" for n in range(1, 5)]
