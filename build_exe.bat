@echo off
REM Builds dist\RANE_VISTA\RANE_VISTA.exe   (run from the project folder; Python 3.10 - 3.13 x64 required)
setlocal
cd /d %~dp0
if not exist .venv (
    py -3.10 -m venv .venv 2>nul || py -3.11 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -3.13 -m venv .venv 2>nul || python -m venv .venv || goto :err
)
call .venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip || goto :err
pip install -r requirements-dev.txt || goto :err
pip install -r requirements-realsense.txt
if errorlevel 1 echo WARNING: pyrealsense2 could not be installed - the build only supports CAMERA_BACKEND=sim.
pyinstaller --noconfirm --clean --distpath dist --workpath build\work build\rane_vista.spec || goto :err
copy /y .env.example dist\RANE_VISTA\.env.example >nul
copy /y check_install.bat dist\RANE_VISTA\check_install.bat >nul
echo.
echo Build complete: dist\RANE_VISTA\RANE_VISTA.exe
echo Next: copy .env.example to dist\RANE_VISTA\.env, fill it in, then run check_install.bat
exit /b 0
:err
echo BUILD FAILED - see the messages above.
exit /b 1