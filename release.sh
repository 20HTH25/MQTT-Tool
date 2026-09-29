#!/usr/bin/env bash
set -euo pipefail

# Full release helper for macOS app.
# Usage:
#   ./release.sh
#   ./release.sh assets/icon.png
#   ./release.sh assets/icon.png assets/app.icns

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PNG_ICON_INPUT="${1:-}"
ICNS_OUTPUT_PATH="${2:-assets/app.icns}"
APP_NAME="MQTT-Tool"
RELEASE_DIR="$PROJECT_ROOT/release"

if [[ "$PNG_ICON_INPUT" != "" ]]; then
  echo "Erzeuge .icns aus: $PNG_ICON_INPUT"
  ./create_icns.sh "$PNG_ICON_INPUT" "$ICNS_OUTPUT_PATH"
fi

echo "Baue App..."
./build_macos.sh "$ICNS_OUTPUT_PATH"

echo "Bereite Release-Ordner vor..."
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

cp -R "$PROJECT_ROOT/dist/$APP_NAME.app" "$RELEASE_DIR/"

if [[ -f "$ICNS_OUTPUT_PATH" ]]; then
  cp "$ICNS_OUTPUT_PATH" "$RELEASE_DIR/"
fi

cat > "$RELEASE_DIR/README.txt" <<EOF
$APP_NAME macOS Release

Inhalt:
- $APP_NAME.app
$( [[ -f "$ICNS_OUTPUT_PATH" ]] && echo "- $(basename "$ICNS_OUTPUT_PATH")" )

Erstellt am: $(date)
EOF

echo
echo "Release fertig:"
echo "  $RELEASE_DIR"
