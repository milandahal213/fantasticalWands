#!/usr/bin/env bash
# noWand installer
# Checks Python version, installs dependencies, and optionally launches the app.

set -e

REQUIRED_MAJOR=3
REQUIRED_MINOR=12   # minimum — tested on 3.14

# ── colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BOLD}[noWand]${RESET} $*"; }
success() { echo -e "${GREEN}[noWand]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[noWand] WARNING:${RESET} $*"; }
die()     { echo -e "${RED}[noWand] ERROR:${RESET} $*" >&2; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════╗${RESET}"
echo -e "${BOLD}║     noWand  —  installer     ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════╝${RESET}"
echo ""

# ── 1. Find a suitable Python ─────────────────────────────────────────────────
info "Looking for Python $REQUIRED_MAJOR.$REQUIRED_MINOR or newer..."

PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=${ver%%.*}; minor=${ver#*.}
        if [[ "$major" -eq "$REQUIRED_MAJOR" && "$minor" -ge "$REQUIRED_MINOR" ]]; then
            PYTHON="$candidate"
            success "Found: $candidate  ($ver)"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    die "Python $REQUIRED_MAJOR.$REQUIRED_MINOR+ not found.\n\
  Download it from https://www.python.org/downloads/ and re-run this script."
fi

# ── 2. Check tkinter is available ─────────────────────────────────────────────
info "Checking tkinter..."
if ! "$PYTHON" -c "import tkinter" &>/dev/null; then
    die "tkinter is not available in this Python installation.\n\
  On macOS: install Python from python.org (not Homebrew) — it includes tkinter.\n\
  On Linux: run  sudo apt install python3-tk  (Debian/Ubuntu)\n\
            or   sudo dnf install python3-tkinter  (Fedora)"
fi
success "tkinter OK"

# ── 3. Create / reuse virtual environment ────────────────────────────────────
VENV_DIR="$(dirname "$0")/.venv"

if [[ -d "$VENV_DIR" ]]; then
    info "Virtual environment already exists — reusing it."
else
    info "Creating virtual environment in .venv ..."
    "$PYTHON" -m venv "$VENV_DIR"
    success "Virtual environment created."
fi

PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── 4. Install / upgrade dependencies ────────────────────────────────────────
info "Installing dependencies from requirements.txt ..."
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$(dirname "$0")/requirements.txt"
success "All packages installed."

# ── 5. macOS Bluetooth permission hint ───────────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    echo ""
    warn "macOS Bluetooth permission:"
    echo "  The first time you run noWand, macOS may ask for Bluetooth access."
    echo "  Click OK — without it the app cannot find LEGO devices."
    echo ""
fi

# ── 6. Offer to launch ───────────────────────────────────────────────────────
echo -e "${BOLD}Installation complete!${RESET}"
echo ""
echo "  To run noWand at any time:"
echo "    .venv/bin/python app.py"
echo ""
read -r -p "Launch noWand now? [Y/n] " answer
answer="${answer:-Y}"
if [[ "$answer" =~ ^[Yy]$ ]]; then
    info "Starting noWand..."
    exec "$PYTHON_VENV" "$(dirname "$0")/app.py"
fi
