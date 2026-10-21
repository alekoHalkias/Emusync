#!/usr/bin/env bash
# EmuSync installer — sets up Python venv and Node dependencies.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

echo "==> Checking prerequisites..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10 or newer." >&2; exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "ERROR: Python 3.10+ required, found $(python3 -V 2>&1)." >&2; exit 1
fi
if ! python3 -c 'import venv, ensurepip' &>/dev/null; then
    echo "ERROR: python3 venv support is missing. On Debian/Ubuntu: sudo apt install python3-venv" >&2; exit 1
fi

echo "==> Setting up Python virtual environment..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
echo "    Python dependencies installed."

echo "==> Creating launcher script..."
cat > "$SCRIPT_DIR/emusync" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$SCRIPT_DIR/emusync.py" "\$@"
EOF
chmod +x "$SCRIPT_DIR/emusync"
echo "    Launcher: $SCRIPT_DIR/emusync"

if command -v npm &>/dev/null && ! command -v node &>/dev/null; then
    echo "    [skip] node not found — GUI dependencies not installed."
elif command -v npm &>/dev/null && [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
    echo "    [skip] Node $(node -v) is too old (need 18+) — GUI dependencies not installed."
elif command -v npm &>/dev/null; then
    echo "==> Installing Node dependencies for GUI..."
    cd "$SCRIPT_DIR/gui" && npm install -q
    echo "    Node dependencies installed."
else
    echo "    [skip] npm not found — GUI dependencies not installed."
    echo "           Install Node.js, then run: cd gui && npm install"
fi

if [ -d "$SCRIPT_DIR/.git" ]; then
    echo "==> Installing git hooks..."
    git -C "$SCRIPT_DIR" config core.hooksPath .githooks
    echo "    Git hooks installed (pre-commit: syntax + CLAUDE.md drift; pre-push: lint + test-changed)."
fi

echo ""
echo "Done! To use the CLI:"
echo "  $SCRIPT_DIR/emusync --help"
echo ""
echo "To run the GUI in development:"
echo "  cd gui && npm run dev"
echo ""
echo "Add $SCRIPT_DIR to PATH or symlink the launcher for system-wide use:"
echo "  ln -s $SCRIPT_DIR/emusync ~/.local/bin/emusync"
echo ""
echo "To run the server automatically on login (recommended for Steam Deck):"
echo "  make install-service"
