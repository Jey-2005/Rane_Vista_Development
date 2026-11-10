@echo off
setlocal
cd /d "%~dp0"
echo Working folder: %cd%

echo.
echo [1/6] Creating virtual environment...
if not exist .venv (
    py -3.10 -m venv .venv || goto :err
) else (
    echo .venv already exists, reusing it
)

echo.
echo [2/6] Activating venv...
call .venv\Scripts\activate.bat || goto :err
python --version

echo.
echo [3/6] Upgrading pip...
python -m pip install --upgrade pip || goto :err

echo.
echo [4/6] Installing requirements...
pip install -r requirements-dev.txt || goto :err
pip install -r requirements-realsense.txt
if errorlevel 1 echo WARNING: pyrealsense2 could not be installed - the build only supports CAMERA_BACKEND=sim.

echo.
echo [5/6] Running PyInstaller...
if not exist build\rane_vista.spec (
    echo ERROR: build\rane_vista.spec not found
    goto :err
)
pyinstaller --noconfirm --clean --distpath dist --workpath build\work build\rane_vista.spec || goto :err

echo.
echo [6/6] Copying support files...
copy /y .env.example dist\RANE_VISTA\.env.example
copy /y check_install.bat dist\RANE_VISTA\check_install.bat

echo.
echo Build complete: dist\RANE_VISTA\RANE_VISTA.exe
echo Next: copy .env.example to dist\RANE_VISTA\.env, fill it in, then run check_install.bat
pause
exit /b 0

:err
echo.
echo BUILD FAILED - see the messages above.
pause
exit /b 1