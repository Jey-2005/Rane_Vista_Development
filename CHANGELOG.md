# Changelog

## 1.1.1 - Windows reliability fixes
- **Fixed: barcode scans were doubled** (`LH123456` became `LLHH112233445566`) with USB keyboard-wedge scanners,
  so variant patterns, barcode checks and duplicate checks failed. A real key press reaches an application-wide
  filter twice (window, then widget); the filter now counts it once. Regression test: `tests/test_wedge.py`.
- Fixed: errors inside button handlers were invisible in the windowed .exe - they are now logged and shown.
- Fixed: silent exit when the data folder was not writable (e.g. installed under Program Files); default data
  folder on Windows is now `%PROGRAMDATA%\RANE_VISTA` and the error message says what to change.
- Fixed: the frameless window covered the Windows taskbar when maximised.
- Fixed: one unexpected camera SDK error could stop the camera thread for good - it now restarts.
- Fixed: a skipped migration surfaced later as `relation "station_process" does not exist`; start-up now stops
  with instructions to run `--migrate` as the schema owner.
- `.env.example` works out of the box (owner account for first start, example station code).
- `pyrealsense2` installs separately (`requirements-realsense.txt`) so a missing camera wheel no longer breaks
  the whole installation; `tzdata` added for correct time zones on Windows.
- New: `RANE_VISTA.exe --check` / `check_install.bat` installation report.
- `run_dev.bat` / `build_exe.bat` accept Python 3.11, 3.12 or 3.13.

## 1.1.0 - Light UI redesign
- VS Code-style title bar, three-section ribbon, Arkite-style Jobs / Steps / Detections / Processes / Connectivity
  pages, station processes, job packages (.vjob).

## 1.0.0 - First release
