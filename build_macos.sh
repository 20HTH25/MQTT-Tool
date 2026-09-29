#!/usr/bin/env bash
set -euo pipefail

# Build a standalone macOS .app via PyInstaller.
# Optional custom icon path:
#   ./build_macos.sh assets/app.icns

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

ICON_PATH="${1:-assets/app.icns}"
APP_NAME="MQTT-Tool"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "PyInstaller nicht gefunden. Installiere zuerst:"
  echo "  pip install pyinstaller"
  exit 1
fi

ICON_ARGS=()
if [[ -f "$ICON_PATH" ]]; then
  ICON_ARGS+=(--icon "$ICON_PATH")
  echo "Verwende Icon: $ICON_PATH"
else
  echo "Kein .icns Icon gefunden unter: $ICON_PATH"
  echo "Baue App ohne eigenes Icon."
fi

rm -rf build dist

if [[ ${#ICON_ARGS[@]} -gt 0 ]]; then
  pyinstaller \
    --windowed \
    --name "$APP_NAME" \
    --clean \
    --noconfirm \
    --collect-all ttkbootstrap \
    "${ICON_ARGS[@]}" \
    app.py
else
  pyinstaller \
    --windowed \
    --name "$APP_NAME" \
    --clean \
    --noconfirm \
    --collect-all ttkbootstrap \
    app.py
fi

echo
echo "Fertig. App liegt hier:"
echo "  $PROJECT_ROOT/dist/$APP_NAME.app"
echo "Vorlagen-Datei (bleibt beim Neu-Bauen erhalten):"
echo "  $HOME/Documents/MQTT-Tool/MQTT-Tool-Vorlagen.json"
