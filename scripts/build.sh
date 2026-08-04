#!/bin/bash
# Build TokenGotchi Windows exe
set -e
pip install pyinstaller pygame watchdog pydantic
pyinstaller tokengotchi.spec
echo "Built: dist/TokenGotchi.exe"
