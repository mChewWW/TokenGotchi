@echo off
pip install pyinstaller pygame watchdog pydantic
pyinstaller tokengotchi.spec
echo Built: dist\TokenGotchi.exe
