"""End-to-end: build a Tamil PDF with headers/page numbers, convert, check.
Skipped unless Tesseract with Tamil and a Noto Sans Tamil font are installed
(the CI workflow installs both)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FONTS = [Path("/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf"),
         Path(__file__).parent / "NotoSansTamil-Regular.ttf"]
FONT = next((f for f in FONTS if f.exists()), None)


def _has_tamil_ocr():
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return "tam" in out.stdout


@pytest.mark.skipif(FONT is None or not _has_tamil_ocr(), reason="needs tesseract-tam + font")
def test_sample_book(tmp_path):
    font = tmp_path / FONT.name
    shutil.copy(FONT, font)
    pdf = tmp_path / "sample.pdf"
    subprocess.run([sys.executable, str(Path(__file__).parent / "make_sample_pdf.py"),
                    str(font), str(pdf)], check=True)
    subprocess.run([sys.executable, "-m", "tamilbook", "convert", str(pdf),
                    "-o", str(tmp_path / "out"), "--strict"], check=True)
    qa = json.loads((tmp_path / "out" / "sample.qa.json").read_text(encoding="utf-8"))
    assert qa["stats"]["missing"] == 0
    txt = (tmp_path / "out" / "sample.txt").read_text(encoding="utf-8")
    assert "இளங்கோ" not in txt                       # author header removed
    assert txt.count("# அத்தியாயம்") == 3           # chapters found
