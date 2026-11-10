# RANE VISTA — architecture

## Folder layout

```text
main.py                         entry point (config, logging, single-instance lock, migrations, login)
vista/
  core/        config.py (.env), security.py (scrypt, Session/permissions), logging_setup.py, geometry.py
  db/          database.py (pool, transactions, migrations), repositories.py (all SQL, parameterised)
  hardware/    camera_base.py, realsense_camera.py, simulated_camera.py, uvc_camera.py,
               camera_worker.py (QThread), projector_control.py (PJLink / RS-232), barcode_scanner.py
  calibration/ calibration.py (marker detection, RANSAC bench plane, bench frame, homographies)
  vision/      detectors.py (object / activity / button / quality + teaching), engine.py
  engine/      steps.py (step catalogue), executor.py (runtime), recorder.py (async DB writer + spool)
  reporting/   export.py (traceability XLSX, CSV)
  app_context.py   service layer: auth, permission checks, audit, settings, teaching persistence, evidence
  demo.py          simulator commissioning (used by --seed-demo and the end-to-end test)
  ui/          theme.py (light), icons.py (vector icon set), dialogs.py (sign-in), dialogs_extra.py (pop-ups),
               main_window.py (title bar, ribbon, status bar), projector_window.py,
               widgets/common.py (ImageView zoom/pan, PropertiesPanel, cards), widgets/bench.py (bench canvas),
               pages/ dashboard, jobs, steps, detections, processes, connectivity, operate, calibration,
                      hardware, users, settings
sql/migrations/  001 initial schema, 002 job properties + station processes + MANAGE_PROCESSES
sql/admin/       least-privilege role script for the DBA
tests/           test_e2e_sim.py (engine + DB), smoke_gui.py (all pages, headless)
```

## Threads

| Thread | Work |
|---|---|
| Qt main | UI, executor (state machine), projector painting |
| CameraWorker | grab → height map → `DetectionEngine.process()` → `states_ready` / `frame_ready` signals |
| ResultRecorder | writes runs/step results; spools to `DATA_DIR/spool/*.jsonl` when the DB is down |
| Vision camera reader (optional) | keeps the latest frame of the UVC camera |
| Serial scanner (optional) | reads lines from the COM port |

Detection states cross threads only through queued Qt signals (copies), so the executor never reads
half-updated state.

## Coordinate systems

1. **Camera pixels** – depth grid; colour is aligned to depth, IR-left is natively aligned.
2. **Bench mm** – X right, Y away from the operator, Z up, origin at the chosen calibration marker.
   `height = Z·K(u,v) + d` is computed per pixel from the fitted bench plane (fast, vectorised).
3. **Projector pixels** – homography `H_bench2proj` from the 3×3 marker grid.
4. **Vision camera pixels** (optional) – homography `H_vision2bench` from the same projected markers.

Detection zones are stored both in camera px (`zone_px`, used for evaluation) and in bench mm
(`zone_mm`, used for projection), so re-calibrating the projector does not require re-teaching.

## Detection algorithms

* **Object** – per pixel of the taught area: *occupied* when it differs from the *without* reference by
  more than `min_diff` and is closer to the *with* reference. Fill is normalised between the taught
  *without* and *with* fill → score 0..1 with hysteresis (`present_score` / `absent_score`) and debounce.
  Pixels more than `occlusion_mm` above the object are counted as occluded; above `occlusion_max` the state
  becomes OCC_PRESENT / OCC_ABSENT (last stable state kept) — prevents false Take/Place while the arm
  passes over.
* **Activity** – fraction of zone pixels between `min_rise_mm` and `max_rise_mm` above the empty-zone
  baseline; dwell ≥ `min_dwell_ms` then leave → counter + 1.
* **Button** – same band logic at press height with hold time; a high arm across the zone is ignored.
* **Quality** – features: grey (texture), Sobel magnitude (shape), HSV histogram. Template search
  ±`search_px` around the taught region. Best class wins if CORRECT, above `min_score` and with
  `min_margin` over the best non-CORRECT class; decision requires `stable_frames` identical evaluations
  and no occlusion (depth above the region).

## Executor semantics

* Released job only; a run gets a UUID, revision and operator.
* Variant filter is evaluated when a step is activated, so steps after the barcode can be variant-specific
  while the variant itself comes from the barcode.
* Containers: sequential, any-order (all children active at once) and repeat-N.
* Quality check policies: `REWORK` (record NG once, keep checking until OK → final OK row),
  `FAIL_RUN`, `ASK_SUPERVISOR` (re-authentication, accept = FORCED, reject = FAIL).
* Station-wide virtual button with function RESET aborts the active run (ABORTED, audited).
* Duplicate barcode policy: BLOCK / WARN / ALLOW (station default, overridable per scan step).

## Database

14 tables in `pdi_inspection` (incl. `station_process`): `role`, `permission`, `role_permission`, `station`, `app_user`,
`user_station`, `job`, `job_variant`, `detection`, `detection_sample` (bytea teaching data), `step`
(tree via `parent_id`), `calibration` (one active per station), `app_setting`, `inspection_run`,
`inspection_step_result`, `audit_log`, `station_process`, plus `schema_version`.

Station processes are mapped onto the runtime switches the executor reads (`AppContext.apply_processes`):
job selection mode / start on scan, auto restart / result display / over-cycle warning, duplicate policy,
evidence capture and the RESET button. Job packages (`JobCatalogRepo.export_package / import_package`) are
gzip-compressed JSON; steps reference detections by name so station-wide detections resolve on the target
station.

Adding a column later: create `sql/migrations/002_<name>.sql`; it is applied once on the next start
(or with `--migrate` when stations use the least-privilege role).
