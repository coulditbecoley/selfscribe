#!/usr/bin/env bash
# Build SelfScribe.app and a shareable zip. Run on a Mac (or the macOS CI job)
# from the repo root:  bash packaging/macos/build.sh
set -euo pipefail

cd "$(dirname "$0")"
python -m pip install --upgrade pip
python -m pip install "../..[build]"
python make_icns.py SelfScribe.icns
rm -rf build dist
python -m PyInstaller --noconfirm SelfScribe.spec

# Ad-hoc sign the whole bundle so macOS keeps the Microphone/Accessibility
# grants between launches. (Not notarized: first launch needs "Open Anyway".)
codesign --force --deep --sign - dist/SelfScribe.app

ARCH="$(uname -m)"
ditto -c -k --keepParent dist/SelfScribe.app "dist/SelfScribe-macOS-${ARCH}.zip"
echo "built dist/SelfScribe-macOS-${ARCH}.zip"
