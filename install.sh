#!/usr/bin/env bash
# EmuSync installer — sets up Python venv and Node dependencies.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

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

if command -v npm &>/dev/null; then
    echo "==> Installing Node dependencies for GUI..."
    cd "$SCRIPT_DIR/gui" && npm install -q
    echo "    Node dependencies installed."
else
    echo "    [skip] npm not found — GUI dependencies not installed."
    echo "           Install Node.js, then run: cd gui && npm install"
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
