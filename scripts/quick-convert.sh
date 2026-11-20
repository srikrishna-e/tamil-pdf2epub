#!/bin/zsh
# Convert Tamil PDFs to EPUB from Finder (used by the "Convert to Tamil eBook"
# Quick Action, see scripts/install-quick-action.sh). Usage:
#   scripts/quick-convert.sh book1.pdf [book2.pdf ...]
# Asks for title, author and the page the story starts on, then converts in
# the background and shows a notification when done. Results go to
# out/<pdf name>/ inside this repo.

REPO="${0:A:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
TAMILBOOK="$REPO/.venv/bin/tamilbook"
FONT="$REPO/tests/NotoSansTamil-Regular.ttf"

notify() {  # notify "title" "message"
  osascript -e 'on run a' -e 'display notification (item 2 of a) with title (item 1 of a)' -e 'end run' "$1" "$2"
}

ask() {  # ask "question" "default"  -> prints answer, exits 1 on Cancel
  osascript -e 'on run a' \
    -e 'set r to display dialog (item 1 of a) default answer (item 2 of a) with title "Tamil eBook" buttons {"Cancel", "OK"} default button "OK"' \
    -e 'return text returned of r' -e 'end run' "$1" "$2" 2>/dev/null
}

if [[ ! -x "$TAMILBOOK" ]]; then
  osascript -e 'display alert "tamilbook is not installed" message "Run: cd tamil-pdf2epub && python3.12 -m venv .venv && .venv/bin/pip install -e ."'
  exit 1
fi

for pdf in "$@"; do
  [[ "${pdf:l}" == *.pdf ]] || continue
  name="${pdf:t:r}"

  title=$(ask "Book title for ${pdf:t}:" "$name") || continue
  author=$(ask "Author (leave blank if unknown):" "") || continue
  start=$(ask "Which PDF page does the story start on? (1 = convert everything)" "1") || continue
  [[ "$start" == <-> && "$start" -ge 1 ]] || start=1

  outdir="$REPO/out/$name"
  mkdir -p "$outdir"
  args=(convert "$pdf" -o "$outdir" --name "$name" --title "$title")
  [[ -n "$author" ]] && args+=(--author "$author")
  [[ -f "$FONT" ]] && args+=(--embed-font "$FONT")
  if [[ "$start" -gt 1 ]]; then
    pages=$("$REPO/.venv/bin/python" -W ignore -c 'import sys,pymupdf;print(pymupdf.open(sys.argv[1]).page_count)' "$pdf")
    args+=(--pages "$start-$pages")
  fi

  # Run in the background so Finder isn't blocked while OCR runs.
  (
    notify "Converting $title" "This takes about 1–2 seconds per page. You'll get a notice when it's done."
    if "$TAMILBOOK" "${args[@]}" > "$outdir/convert.log" 2>&1; then
      summary=$(grep -m1 '^✓' "$outdir/convert.log" | sed 's/^✓ //')
      notify "Done: $title" "${summary:-Finished}"
      open "$outdir/$name.qa.html"
      open -R "$outdir/$name.epub"
    else
      notify "Failed: $title" "See convert.log in out/$name"
      open -R "$outdir/convert.log"
    fi
  ) &!
done
