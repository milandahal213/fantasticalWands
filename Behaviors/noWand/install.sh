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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

# ── 3. Check for libcairo (required by cairosvg) ─────────────────────────────
info "Checking for libcairo (needed for SVG icons)..."

CAIRO_OK=false
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS: look for the dylib via Homebrew or system paths
    if find /usr/local/lib /opt/homebrew/lib /usr/lib 2>/dev/null \
            -name "libcairo*.dylib" -quit | grep -q .; then
        CAIRO_OK=true
    fi
else
    # Linux: ldconfig knows about installed shared libraries
    if ldconfig -p 2>/dev/null | grep -q libcairo; then
        CAIRO_OK=true
    fi
fi

if [[ "$CAIRO_OK" == false ]]; then
    echo ""
    warn "libcairo was not found — SVG icons will not render."
    echo ""
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "  Install it with Homebrew:"
        echo "    brew install cairo"
        echo ""
        echo "  Don't have Homebrew? Install it first:"
        echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    else
        echo "  Install it with your package manager:"
        echo "    Ubuntu / Debian:  sudo apt install libcairo2"
        echo "    Fedora:           sudo dnf install cairo"
        echo "    Arch:             sudo pacman -S cairo"
    fi
    echo ""
    read -r -p "Continue anyway (app works without icons)? [Y/n] " cairo_answer
    cairo_answer="${cairo_answer:-Y}"
    if [[ ! "$cairo_answer" =~ ^[Yy]$ ]]; then
        echo "Install libcairo and re-run this script."
        exit 0
    fi
else
    success "libcairo found"
fi

# ── 4. Create / reuse virtual environment ────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ -d "$VENV_DIR" ]]; then
    info "Virtual environment already exists — reusing it."
else
    info "Creating virtual environment in .venv ..."
    "$PYTHON" -m venv "$VENV_DIR"
    success "Virtual environment created."
fi

PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── 5. Install / upgrade dependencies ────────────────────────────────────────
info "Installing dependencies from requirements.txt ..."
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$SCRIPT_DIR/requirements.txt"
success "All packages installed."

# ── 6. Verify cairosvg actually works (does a real SVG render) ───────────────
info "Verifying SVG rendering..."
SVG_TEST='<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="5" fill="red"/></svg>'
CAIRO_RUNTIME_OK=false

if "$PYTHON_VENV" - <<'PYEOF' 2>/dev/null
import cairosvg, io
svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="5" fill="red"/></svg>'
cairosvg.svg2png(bytestring=svg, output_width=10, output_height=10)
print("ok")
PYEOF
then
    CAIRO_RUNTIME_OK=true
fi

if [[ "$CAIRO_RUNTIME_OK" == true ]]; then
    success "SVG rendering works — icons will display correctly."
else
    echo ""
    warn "cairosvg is installed but failed to render a test SVG."
    echo "  This usually means libcairo is installed in a location Python can't find."
    echo ""
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "  Try these steps:"
        echo "    1. Make sure cairo is installed:  brew install cairo"
        echo "    2. If you have both Intel and Apple Silicon Homebrew, make sure"
        echo "       you're using the one that matches your Python architecture."
        echo "    3. Re-run this installer after installing cairo."
        echo ""
        echo "  The app will still run, but device icons will be replaced with text labels."
    else
        echo "  Try:  sudo apt install libcairo2  (or equivalent for your distro)"
        echo "  Then re-run this installer."
        echo ""
        echo "  The app will still run, but device icons will be replaced with text labels."
    fi
    echo ""
fi

# ── 7. macOS Bluetooth permission hint ───────────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    echo ""
    warn "macOS Bluetooth permission:"
    echo "  The first time you run noWand, macOS may ask to allow Bluetooth access."
    echo "  Click OK — without it the app cannot discover LEGO devices."
fi

# ── 8. Offer to launch ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Installation complete!${RESET}"
echo ""
echo "  To run noWand at any time:"
echo "    cd $(basename "$SCRIPT_DIR") && .venv/bin/python app.py"
echo ""
read -r -p "Launch noWand now? [Y/n] " answer
answer="${answer:-Y}"
if [[ "$answer" =~ ^[Yy]$ ]]; then
    info "Starting noWand..."
    exec "$PYTHON_VENV" "$SCRIPT_DIR/app.py"
fi
