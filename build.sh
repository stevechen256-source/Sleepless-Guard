#!/bin/bash
# Compile locally; no system power settings, authorization, or app launch.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$ROOT/build"
APP="$DEST/SleeplessCN.app"
TARGET="${TARGET:-arm64-apple-macos26.0}"
command -v swiftc >/dev/null || { echo 'Install Apple Command Line Tools first: xcode-select --install' >&2; exit 1; }
if [ -L "$DEST" ] || [ -L "$APP" ]; then
  echo 'Build destinations must not be symlinks.' >&2; exit 1
fi
mkdir -p "$DEST"
STAGE="$(mktemp -d "$DEST/.stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
BUNDLE="$STAGE/SleeplessCN.app"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
echo 'Building Sleepless CN Guard...'
swiftc -O -parse-as-library -target "$TARGET" -framework AppKit -framework ServiceManagement \
  "$ROOT/App.swift" "$ROOT/PowerState.swift" -o "$BUNDLE/Contents/MacOS/SleeplessCN"
cp "$ROOT/Info.plist" "$BUNDLE/Contents/Info.plist"
cp "$ROOT/assets/Sleepless.icns" "$BUNDLE/Contents/Resources/Sleepless.icns"
cp -R "$ROOT/locales/"*.lproj "$BUNDLE/Contents/Resources/"
cp "$ROOT/grant.sh" "$ROOT/NOTICE.md" "$ROOT/LICENSE" "$BUNDLE/Contents/Resources/"
cp "$ROOT/scripts/diagnostics.py" "$BUNDLE/Contents/Resources/"
chmod 755 "$BUNDLE/Contents/Resources/grant.sh" "$BUNDLE/Contents/MacOS/SleeplessCN"
/usr/bin/codesign --force --deep --sign - "$BUNDLE"
/usr/bin/codesign --verify --strict "$BUNDLE"
# The only replaced output is this repository's generated build directory.
rm -rf "$APP"
mv "$BUNDLE" "$APP"
echo "Built: $APP"
echo 'No app was installed or started, and no sleep settings were changed. Run ./install.sh to install.'
