# PyInstaller spec - build with build_exe.bat (one-folder build: faster start, fewer AV false positives)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = Path(SPECPATH).parent

binaries = []
try:
    binaries += collect_dynamic_libs("pyrealsense2")   # realsense2.dll etc.
except Exception:
    pass

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=[(str(ROOT / "sql"), "sql"), (str(ROOT / "assets"), "assets"), (str(ROOT / ".env.example"), "."),
           (str(ROOT / "README.md"), "."), (str(ROOT / "check_install.bat"), ".")],
    hiddenimports=["psycopg_binary", "psycopg_pool", "pyrealsense2", "PySide6.QtCharts", "PySide6.QtSvg", "serial",
                   "serial.tools.list_ports"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RANE_VISTA", console=False,
          icon=str(ROOT / "assets" / "rane_vista.ico"), version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="RANE_VISTA")
