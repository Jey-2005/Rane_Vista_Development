# RANE VISTA — Visual Inspection & Smart Task Assistance

In-house operator guidance system for rack & pinion PDI inspection, built to replace the Arkite
assembly-inspection module. A depth camera watches the bench, a short-throw projector paints the next
action directly on the part, and every check is recorded against the part barcode with evidence images.

| | |
|---|---|
| Frontend | PySide6 (Qt 6) desktop app - light theme, VS Code-style title bar, three-section ribbon, Arkite-style pages - plus a full-screen projector window |
| Backend | Python 3.11 service layer, detection engine, job executor |
| Database | PostgreSQL (`PDI_Inspection`, schema `pdi_inspection`) |
| Hardware | Intel RealSense D456 / D457, Optoma ZH406ST, USB or serial barcode scanner, optional 2D vision camera |
| Delivery | PyInstaller one-folder build → `RANE_VISTA.exe` |

---

## 1. What it does

```text
Depth camera ──► height map (mm above calibrated bench) ──► detection engine ──► job executor ──► operator screen
                                                                                         │      └► projector window
                                                                                         └► result recorder ──► PostgreSQL + evidence JPEGs
```

**Detections**

| Type | How it is detected | Used for |
|---|---|---|
| Object | Depth (or IR) compared with taught *with* / *without* snapshots; occlusion by the operator's arm keeps the last stable state | Part in fixture, gauge in holder, scanner in holder |
| Activity | Hand inside a zone for a minimum dwell, completed on leave | Gauge applied on the part |
| Virtual button | Fist held at a low height band over a projected button | Station **RESET**, confirmations |
| Quality check | Live region compared with CORRECT / WRONG / MISSING class samples (texture NCC, edge-shape NCC or colour histogram; **AUTO** picks the best by leave-one-out at teach time) | Bellow clips, crimps, OBJ, mounting holes, firewall, locks … |

**Step types:** Numbered step, Composite (sequential / any order / repeat), Place, Take, Activity, Press,
Quality check (rework / fail part / supervisor decision), Scan barcode, Snapshot, Set variable, Delay,
Operator decision (e.g. gauge OK / NOT OK), Work instruction.

---

## 2. User interface

```text
┌ Title bar ─ logo · File Edit View Run Tools Help · ← → · [ command centre: active job / Ctrl+P search ] · user · role · sign out · ─ □ ✕ ┐
├ Ribbon ─ Configure: Dashboard Jobs Steps Detections Processes Connectivity | Production: Operate Calibration Hardware | Administration: Users Settings Help About ┤
├ Page ─ Arkite layout: list / tree · workspace (canvas, tabs) · Properties panel ┤
└ Status bar ─ 3D sensor FPS · run/edit mode · calibration · database · last scan ············· errors / warnings chip (opens message log) ┘
```

| Page | What it is for |
|---|---|
| Dashboard | Output, pass/fail, first-pass yield, cycle time, NG pareto, slowest steps, recent inspections |
| Jobs | Job cards (variants link, status, untaught warning); Properties: name, image, product identifier, part number, expected cycle time, variants, release |
| Steps | Step tree (numbered, nested, ○ waits / ▽ instant / ⚠ missing detection), New Step by category, indent/outdent; Projector and Screen previews; Properties |
| Detections | Station-wide / job-specific tree with live state; Teaching (without/with snapshots, class samples, cursor position in mm), Fine tune (live score + thresholds), Projector (drag to shift projection); Properties |
| Processes | Station automation: job selection (manual or automatic from barcode), inspection cycle, duplicate barcode check, evidence capture, reset |
| Connectivity | Device cards for projector, operator screen, 3D sensor, RGB, vision camera, scanner, database - configuration and live streams open as pop-ups |
| Operate | Operator screen: steps, amber instruction banner, live camera, part / cycle time / result, counters, messages |
| Calibration | Four-step wizard: projector output → automatic markers → review → verify grid |
| Hardware | Diagnostics: four live streams, frame rate, valid depth, bench noise, projector test patterns, scanner test, simulator |
| Users / Settings | Inline user editing with station access and role matrix; searchable settings that save immediately |

Pop-ups: command centre (Ctrl+P), File > Open / Save job package (`.vjob`), File > Export inspection data (Ctrl+E),
Help (F1), keyboard shortcuts (Ctrl+K), message log, About.

---

## 3. Arkite → VISTA feature map

| Arkite feature | VISTA | Note |
|---|---|---|
| Processes tab | ✅ | Station processes stored per station (`station_process`), audited when changed |
| Project export / import | ✅ | Job package `.vjob` with variants, steps and teaching data |
| Jobs, variants, numbered / composite steps | ✅ | Composite *any order* and *repeat* supported |
| Object / Activity / Virtual button / Quality check | ✅ | Same teach workflow (with / without, class snapshots) |
| Teaching → Finetune (detection rate, IR, occlusion) | ✅ | Thresholds editable per detection, live score shown |
| Calibration wizard (click each projected marker) | ✅ **improved** | Markers are found **automatically**, 3×3 grid, RMS error reported |
| Job Selection process | ✅ **improved** | Variant (LH/RH) chosen **automatically from the barcode pattern**; scan starts the run |
| Check step with *If expected / bad / missing* branches | ✅ simplified | Per-step policy: rework until OK, fail part, or supervisor decision |
| Set variable (`Thread Ring NoGo gauge 1 ← 'PASS'`) | ✅ | Recorded in traceability |
| Snapshot | ✅ | Evidence JPEG with station / time / barcode stamp |
| Barcode/QR scanner module | ✅ | Keyboard-wedge or serial COM |
| Log tables / dashboards | ✅ **improved** | Dashboard (FPY, NG pareto, slow steps, recent inspections) and XLSX export with one column per check and linked evidence (replaces the manual image-column report). The audit trail is still recorded in the database; there is no separate on-screen page for it |
| Versioning / approval | ✅ | DRAFT → RELEASED revisions, segregation of duties on release |
| Audit logging | ✅ | Append-only audit trail at DB level |
| — | ✅ **new** | Duplicate-barcode block, supervisor override with re-authentication, local result spool when the DB is offline, simulator for training & regression tests, RBAC with station access |
| Picking bins, materials, smart tools, DMX pick-to-light, Open Protocol, CAD/CAM, OCR, translations, recordings, experience levels, tasks, server licensing | ❌ removed | Not used by the PDI inspection module |

---

## 4. Hardware build per station

| Item | Recommendation |
|---|---|
| Depth camera | **Intel RealSense D456** (USB-C, IP65). D457 also works, but ships in GMSL mode: open the small cap and move the interface switch to **USB** before use on Windows. Intel supports its USB port for production/debug only. |
| Mounting | Camera 0.9–1.3 m above the bench, looking down (D45x minimum depth ≈ 0.52 m). Rigid mount; any movement needs recalibration. |
| Projector | Optoma ZH406ST over HDMI as an extended Windows display at 1920×1080, **Windows scaling 100 %**. LAN cable for PJLink control (TCP 4352). |
| PC | Existing box PC class is fine (Core Ultra / i5+, 16 GB RAM, USB 3 port). |
| Scanner | Any USB HID (keyboard-wedge) scanner, or serial / virtual-COM. |
| Optional | High-resolution 2D UVC/industrial camera with lens for small-feature quality checks (`VISION_CAMERA_INDEX`). |

At ~1 m the D45x resolves roughly 2–2.5 mm per pixel: ideal for presence of gauges, part and hand
activity. For clip / crimp level checks prefer the optional vision camera.

---

## 5. Installation

### 5.1 Database (once per plant / server)
1. PostgreSQL 14+ running, database `PDI_Inspection` created.
2. First start of the app with the **owner** account (e.g. `postgres`) creates schema `pdi_inspection`
   and seeds roles/permissions (`RANE_VISTA.exe --migrate` does only this and exits).
3. Create the least-privilege application login and switch the stations to it:
   ```bat
   psql -U postgres -d PDI_Inspection -v app_pw="'<strong-password>'" -f sql\admin\least_privilege_role.sql
   ```
   The `vista_app` role cannot update/delete the audit trail or delete inspection history.

### 5.2 Quick start from source (developer PC)
```bat
copy .env.example .env        REM then edit DB_PASSWORD, STATION_CODE; CAMERA_BACKEND=sim without a camera
run_dev.bat --check           REM installation report - every line should be OK or WARN
run_dev.bat                   REM start (add --seed-demo with CAMERA_BACKEND=sim for a ready-made demo job)
```

### 5.2a Build the executable (developer PC)
```bat
build_exe.bat
```
Output: `dist\RANE_VISTA\RANE_VISTA.exe` (one-folder build). Python 3.11 x64 recommended.

### 5.3 Station PC
1. Install the **Intel RealSense SDK 2.0** (driver + firmware tools); update camera firmware with RealSense Viewer.
2. Copy `dist\RANE_VISTA` to e.g. `C:\RANE_VISTA`.
3. Copy `.env.example` to `.env`, fill in `DB_*`, `STATION_CODE`, `DATA_DIR`. Restrict `.env` NTFS
   permissions to administrators and the station user.
4. Start `RANE_VISTA.exe`. On a new database you are asked to create the first administrator
   (there is **no default password**).

### 5.4 Try it without hardware
Set `CAMERA_BACKEND=sim` and start with `RANE_VISTA.exe --seed-demo`. The simulator is calibrated,
detections are taught and a released demo job (`CC21-LH-DEMO`, mirroring the CC21 LH Arkite flow) is
created. Use **Hardware → Simulator controls** to place parts, move the hand and switch clip states.

---

## 6. Commissioning a station

1. **Connectivity** – all device cards show a green tick; open *Configure…* on the projector card to set the
   output display and PJLink address.
2. **Calibration** – choose the projector display, rotation/mirroring, *Apply output*. Clear the bench,
   *Run calibration*. Accept when the reprojection error is below ~2 px; *Save*. *Test pattern* projects a
   100 mm grid with the origin for verification.
3. **Detections** – select the job (Jobs page or Ctrl+P), create detections (job-specific or station-wide), draw the working zone
   on the camera image and teach:
   * Object: *Capture without* (object removed) → *Capture with* (object placed) → *Teach*.
   * Activity / Button: *Capture empty zone* → *Teach*; perform the activity and watch the counter.
   * Quality check: classes *Expected / Bad / Missing* (add more WRONG classes for specific defects),
     add several samples per class under realistic variation, algorithm *AUTO* → *Teach*.
   * Create one station-wide **Virtual button** with *Station function = RESET*.
4. **Jobs / Steps** – create the job, define variants with barcode patterns (e.g. `LH\d{6}`), build the step
   tree (drag or indent to nest), link detections.
5. **Processes** – choose manual or automatic (barcode) job selection, the duplicate barcode policy and evidence
   capture.
6. **Release** – a QUALITY/ADMIN user (different from the last editor) releases the revision. Any later
   edit returns the job to DRAFT; operators keep running only released jobs.
7. **Users** – create operators/supervisors, assign station access. Temporary passwords are shown once and
   must be changed at first sign-in.

---

## 7. Daily operation

* Operator signs in (user name or employee code), selects the job once per shift.
* Scanning a part starts an inspection; the projector highlights the next action in amber, turns green on
  completion, red on a bad quality result.
* Bad quality result → rework until correct (default), or fail / supervisor decision as configured per step.
* *Supervisor override* forces the active step after re-authentication by a user with OVERRIDE permission;
  it is recorded as FORCED with the supervisor's identity.
* Result banner PASS / FAIL on screen and on the bench; the next inspection starts automatically.

---

## 8. Security & compliance (ISO 27001 / IATF 16949 / TISAX support)

| Control | Implementation |
|---|---|
| Authentication | scrypt password hashes, policy, lockout after N failures, forced change of temporary passwords, idle sign-out for engineering roles |
| Authorisation | Role → permission matrix in the DB; checks in the service layer, not only hidden buttons; station access per user |
| Least privilege | Dedicated `vista_app` DB role; audit trail append-only; no deletion of inspection history |
| Change management | Job DRAFT/RELEASED revisions, segregation of duties on release, every edit audited |
| Traceability | Run + step results with timestamps, operator, revision, variant, evidence images |
| Secrets | `.env` only (never in code / DB / logs); log redaction of password-like values |
| Injection | Parameterised SQL everywhere; CSV/XLSX formula-injection guard on export |
| Availability | Results spooled locally if the DB is unreachable and replayed automatically; dangling runs closed at startup |

**Backup:** schedule `pg_dump -Fc PDI_Inspection` daily and back up `DATA_DIR\evidence`. Test restores
quarterly (restore to a scratch DB and open a few runs in *Traceability*).

---

## 9. Tests

```bat
set VISTA_TEST_ENV=C:\path\to\test.env    REM points to a TEST database - the test schemas are dropped!
python -m pytest tests -q                  REM end-to-end: calibration, teaching, inspections, DB, evidence
python tests\smoke_gui.py screenshots      REM headless GUI smoke test of every page
```

---

## 10. Troubleshooting

Run **`check_install.bat`** (or `RANE_VISTA.exe --check`) first. It checks Python and packages, `.env`, the data
folder, the database and schema version, the RealSense camera (USB 2 / D457 switch), displays and display
scaling, and serial ports, and writes `DATA_DIR\logs\check_report.txt`. Unexpected errors are always written to
`DATA_DIR\logs\vista.log` and shown in a dialog with details.

| Symptom | Cause / fix |
|---|---|
| "Missing required setting …" at start | `.env` missing or incomplete - copy `.env.example` to `.env` next to the exe/`main.py` |
| "Cannot connect to PostgreSQL" | Server stopped, wrong password, or `DB_USER=vista_app` before running the DBA script |
| "Database schema is out of date" | Stations use `vista_app`: run `RANE_VISTA.exe --migrate` once with the owner account |
| "Cannot create the data folder" | Set `DATA_DIR` to a writable folder (default `C:\ProgramData\RANE_VISTA`) |
| Status bar "Camera offline" | USB 3 cable/port; D457 interface switch on USB; `pyrealsense2` installed (`check_install.bat`) |
| Barcode rejected / wrong variant | Check the variant barcode pattern; scanner must send Enter (CR) after the code |
| Projections misplaced | Projector display scaling must be 100 %; recalibrate after moving camera or projector |

## 11. Known limitations / next steps

* Projection uses a bench-plane homography; outlines are drawn at the footprint of an object. Very tall
  objects far from the optical axis show a small parallax offset — use *Projection shift X/Y* per detection.
* RS-232 command strings for the projector follow Optoma's common format; verify against the ZH406ST
  RS-232 sheet (PJLink over LAN is the primary, standards-based channel).
* Vision QC on the RealSense colour stream is limited by its resolution; add the optional 2D camera for
  fine features.
* Validate every quality check with a defect library (known good / known bad parts) before release —
  record the result in your PPAP/MSA documentation.
