@echo off
REM One-click build: produces dist\DotA改键精灵.exe (single-file, admin, no icon)
cd /d "%~dp0"
pip install pyinstaller
pyinstaller --noconfirm --clean dota_warkey.spec
echo.
echo Done. Output: %~dp0dist\DotA改键精灵.exe
pause
