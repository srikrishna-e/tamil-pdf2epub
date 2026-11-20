#!/bin/zsh
# Installs the Finder Quick Action "Convert to Tamil eBook" (right-click a PDF).
REPO="${0:A:h:h}"
SRC="$REPO/scripts/Convert to Tamil eBook.workflow"
DST="$HOME/Library/Services/Convert to Tamil eBook.workflow"
rm -rf "$DST" && cp -R "$SRC" "$DST"
/usr/bin/sed -i '' "s|__REPO__|$REPO|g" "$DST/Contents/document.wflow"
/System/Library/CoreServices/pbs -update 2>/dev/null
echo "Installed: right-click a PDF in Finder → Quick Actions → Convert to Tamil eBook"
