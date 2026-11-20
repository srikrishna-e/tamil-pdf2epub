# Contributing / பங்களிப்பு

All help is welcome — you don't need to be a programmer.

## Without coding
- **Proofread a book**: pick an issue labelled `proofreading`, follow the
  proofreading workflow in the README, open a pull request with the fixed `.txt`.
- **Report a bad conversion**: open an issue with the PDF page number and a
  screenshot. Attach the `.qa.html` report if you can.
- **Improve categories**: the keyword lists in `tamilbook/categorize.py` are
  plain Tamil words. Add better ones and open a pull request.

## With coding
- Keep the QA guarantee: any change that alters text must keep
  `pytest` green, especially `test_qa_catches_dropped_paragraph`.
- Add a test for every bug you fix (synthetic `Page`/`Line` objects in
  `tests/test_pipeline.py` are quickest).
- Ideas: legacy font converters (Bamini/TAM/TAB → Unicode) instead of OCR,
  other OCR engines, footnote handling, two-column layouts, a Tamil
  spell-check pass to flag likely OCR errors.

## Adding books to the library
Only public-domain, nationalised (நாட்டுடைமை) or permission-granted works.
State the source and rights status in your pull request.
