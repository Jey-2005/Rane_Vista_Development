@echo off
REM Diagnoses the installation and writes DATA_DIR\logs\check_report.txt
cd /d %~dp0
if exist RANE_VISTA.exe (
    RANE_VISTA.exe --check
) else (
    if exist .venv\Scripts\python.exe ( .venv\Scripts\python.exe main.py --check ) else ( python main.py --check )
)
pause
