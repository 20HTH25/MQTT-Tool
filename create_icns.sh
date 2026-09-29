#!/usr/bin/env bash
set -euo pipefail

# Convert a source image (PNG/JPG) to macOS .icns.
# Example:
#   ./create_icns.sh assets/icon-1024.png assets/app.icns

if [[ "${1:-}" == "" ]]; then
  echo "Usage: ./create_icns.sh <input-image> [output-icns]"
  exit 1
fi

INPUT_IMAGE="$1"
OUTPUT_ICNS="${2:-assets/app.icns}"

if [[ ! -f "$INPUT_IMAGE" ]]; then
  echo "Datei nicht gefunden: $INPUT_IMAGE"
  exit 1
fi

WORK_DIR="$(mktemp -d)"
ICONSET_DIR="$WORK_DIR/AppIcon.iconset"
mkdir -p "$ICONSET_DIR"

# Required icon sizes for iconutil.
sips -z 16 16     "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
sips -z 32 32     "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
sips -z 32 32     "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
sips -z 64 64     "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
sips -z 128 128   "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
sips -z 256 256   "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
sips -z 256 256   "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
sips -z 512 512   "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
sips -z 512 512   "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$INPUT_IMAGE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null

mkdir -p "$(dirname "$OUTPUT_ICNS")"
iconutil -c icns "$ICONSET_DIR" -o "$OUTPUT_ICNS"

rm -rf "$WORK_DIR"
echo "Icon erstellt: $OUTPUT_ICNS"
