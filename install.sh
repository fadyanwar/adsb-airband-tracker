#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="/usr/local/bin/adsb"

echo "Installing adsb command..."

# Check dependencies
for cmd in python3 dump1090-mutability; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing dependency: $cmd"
        echo "Install with: sudo apt install dump1090-mutability (and python3)"
        exit 1
    fi
done

if ! python3 -c "import requests" 2>/dev/null; then
    echo "Missing Python module: requests"
    echo "Install with: pip install requests"
    exit 1
fi

# Copy the tracker script
cp "$SCRIPT_DIR/adsb_tracker.py" "$TARGET"
chmod +x "$TARGET"

# Fix shebang if needed
sed -i '1i#!/usr/bin/env python3' "$TARGET" 2>/dev/null || true
# Remove duplicate shebangs
python3 - "$TARGET" << 'PY'
import sys
p = sys.argv[1]
lines = open(p).read().splitlines()
out = []
seen_shebang = False
for l in lines:
    if l.startswith("#!"):
        if seen_shebang:
            continue
        seen_shebang = True
    out.append(l)
open(p, "w").write("\n".join(out) + "\n")
PY
chmod +x "$TARGET"

echo "Installed: $TARGET"
echo "Run with: adsb [--freq 118.5]"
