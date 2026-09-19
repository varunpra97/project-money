#!/bin/bash
# Builds the Pulse app and launches it in the iPhone Simulator.
# Usage: bash run-sim.sh
set -e
cd "$(dirname "$0")"

echo "-> Checking Xcode command line tools..."
if ! xcode-select -p >/dev/null 2>&1; then
  echo "No command line tools found. Run: sudo xcode-select -s /Applications/Xcode.app"
  exit 1
fi

echo "-> Finding an iPhone simulator..."
LINE=$(xcrun simctl list devices available 2>/dev/null | grep "iPhone" | head -1)
UDID=$(echo "$LINE" | grep -oE '[0-9A-F-]{36}')
NAME=$(echo "$LINE" | sed -E 's/^ *//; s/ \([0-9A-F-]{36}\).*//')
if [ -z "$UDID" ]; then
  echo "No iPhone simulator available."
  echo "Open Xcode -> Settings -> Platforms, download an iOS Simulator runtime, then re-run this script."
  exit 1
fi
echo "   Using: $NAME ($UDID)"

echo "-> Building Pulse (a few minutes on first run)..."
xcodebuild -project Pulse.xcodeproj -scheme Pulse -configuration Debug \
  -destination "platform=iOS Simulator,id=$UDID" \
  -derivedDataPath build build

echo "-> Booting simulator..."
xcrun simctl boot "$UDID" 2>/dev/null || true
open -a Simulator || true

echo "-> Installing and launching..."
APP=$(find build/Build/Products/Debug-iphonesimulator -maxdepth 1 -name "Pulse.app" | head -1)
if [ -z "$APP" ]; then echo "Build produced no app bundle."; exit 1; fi
xcrun simctl install "$UDID" "$APP"
xcrun simctl launch "$UDID" com.varunprakash.pulse
echo "Done - Pulse should now be open in the Simulator."
