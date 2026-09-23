@echo off
REM Builds a single exe at dist\UsageTray.exe
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --onefile --noconsole --name UsageTray usage_tray.pyw
