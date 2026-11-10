"""Demo / commissioning helper for the simulator (CAMERA_BACKEND=sim).

`RANE_VISTA --seed-demo` calibrates the simulated bench, creates and teaches detections and
builds a released demo job that mirrors the Arkite CC21 LH inspection flow, so the complete
system can be explored without hardware. The same routine drives the automated end-to-end test.
"""
from __future__ import annotations


from vista.calibration.calibration import find_marker, marker_grid, solve_calibration
from vista.engine.steps import default_params
from vista.vision.detectors import teach_object, teach_quality, teach_zone_baseline


def _grab(cam, ctx, n=5):
    frames = []
    for _ in range(n):
        f = cam.read()
        if ctx.calibration is not None:
            f.height_mm = ctx.calibration.height_map(f.depth_mm)
        frames.append(f)
    return frames


def calibrate_sim(ctx, cam) -> float:
    saved = {o.name: o.present for o in cam.objects}
    for o in cam.objects:
        o.present = False
    grid = marker_grid(*cam.proj_size)
    cam.set_markers([])
    ref = cam.read().color
    pts = []
    for p in grid:
        cam.set_markers([p])
        pts.append(find_marker(ref, cam.read().color))
    cam.set_markers([])
    f = cam.read()
    cal = solve_calibration(f.intrinsics, f.depth_mm, pts, grid, cam.proj_size, 6, 8)
    ctx.calibration = cal
    ctx.calibrations.save(cal.to_dict(), cal.rms_px, ctx.session.user_id)
    for o in cam.objects:
        o.present = saved[o.name]
    return cal.rms_px


def _pad(rect, px=12):
    x, y, w, h = rect
    return [x - px, y - px, w + 2 * px, h + 2 * px]


def seed_demo(ctx, cam) -> int:
    """Creates the demo job. Returns job id. Requires an ADMIN/ENGINEER session."""
    if ctx.calibration is None:
        calibrate_sim(ctx, cam)
    D = ctx.detections
    existing = [j for j in ctx.jobs.list(True) if j["code"] == "CC21-LH-DEMO"]
    if existing:
        return existing[0]["id"]
    job_id = ctx.jobs.create("CC21-LH-DEMO", "CC21 rack & pinion PDI (demo)", "CC21-LH", "Simulator demo job",
                             ctx.session.user_id)
    ctx.jobs.save_variants(job_id, [
        {"code": "LH", "name": "Left hand drive", "barcode_regex": r"LH\d{6}"},
        {"code": "RH", "name": "Right hand drive", "barcode_regex": r"RH\d{6}"}])

    def obj(name, job=True, group="FIXTURE"):
        det_id = D.create(job_id if job else None, name, group, "OBJECT", "DEPTH", {})
        so = cam.get(name)
        cam.set_present(name, False)
        without = [f.height_mm for f in _grab(cam, ctx)]
        cam.set_present(name, True)
        frames = _grab(cam, ctx)
        model, arrays = teach_object(_pad(so.rect), without, [f.height_mm for f in frames], "DEPTH", "NARROW",
                                     [f.height_mm for f in frames])
        ctx.store_teaching(det_id, model, arrays)
        return det_id

    def zone(name, rect, det_type, params=None, job=True, group="ACTIVITY"):
        det_id = D.create(job_id if job else None, name, group, det_type, "DEPTH", params or {})
        frames = _grab(cam, ctx)
        model, arrays = teach_zone_baseline(rect, [f.height_mm for f in frames])
        ctx.store_teaching(det_id, model, arrays)
        return det_id

    def qc(name):
        det_id = D.create(job_id, name, "QUALITY CHECK", "QUALITY", "COLOR", {})
        so = cam.get(name)
        roi = list(so.rect)
        samples = []
        x, y, w, h = roi
        for state, cls, ctype in (("good", "Expected result", "CORRECT"), ("bad", "Bad result", "WRONG"),
                                  ("missing", "Missing", "MISSING")):
            cam.set_qc(name, state)
            for f in _grab(cam, ctx, 2):
                samples.append((cls, ctype, f.color[y:y + h, x:x + w].copy()))
        cam.set_qc(name, "good")
        hf = [f.height_mm for f in _grab(cam, ctx)]
        model, arrays = teach_quality(roi, samples, "AUTO", hf)
        ctx.store_teaching(det_id, model, arrays, samples)
        return det_id

    # scene starts with the part not loaded
    cam.set_present("JOB LOADING", False)
    d_reset = zone("RESET", list(cam.get("RESET").rect), "BUTTON", {"function": "RESET"}, job=False, group="")
    d_job = obj("JOB LOADING")
    d_scan = obj("BARCODE SCANNER", group="GAUGE")
    d_pp = obj("P POINT GAUGE", group="GAUGE")
    d_go = obj("THREAD RING GO GAUGE", group="GAUGE")
    d_act = zone("P POINT GAUGE ASSY", [250, 205, 120, 80], "ACTIVITY")
    d_clh = qc("BELLOW CLIP LH")
    d_crh = qc("BELLOW CLIP RH")
    cam.set_present("JOB LOADING", False)
    _ = d_reset

    J = ctx.jobs

    def step(parent, stype, name, det=None, sort=0, **params):
        p = default_params(stype)
        p.update(params)
        return J.create_step(job_id, parent, stype, name, sort, p, det)

    s1 = step(None, "NUMBERED", "Load and identify", sort=1)
    step(s1, "PLACE", "Place Object JOB LOADING", d_job, 1)
    step(s1, "TAKE", "Take Object BARCODE SCANNER", d_scan, 2)
    step(s1, "WAIT_BARCODE", "Wait for barcode", None, 3)
    step(s1, "PLACE", "Place Object BARCODE SCANNER", d_scan, 4)
    step(s1, "SNAPSHOT", "Snapshot", None, 5)
    s2 = step(None, "NUMBERED", "QC PASS", sort=2)
    c = step(s2, "COMPOSITE", "Visual checks - any order", None, 1, order="ANY_ORDER")
    step(c, "QUALITY_CHECK", "Check BELLOW CLIP LH", d_clh, 1)
    step(c, "QUALITY_CHECK", "Check BELLOW CLIP RH", d_crh, 2)
    s3 = step(None, "NUMBERED", "P POINT GAUGE", sort=3)
    step(s3, "TAKE", "Take Object P POINT GAUGE", d_pp, 1)
    step(s3, "ACTIVITY", "Activity P POINT GAUGE ASSY", d_act, 2)
    step(s3, "PLACE", "Place Object P POINT GAUGE", d_pp, 3)
    step(s3, "SET_VARIABLE", "P POINT GAUGE result", None, 4, variable="P_POINT", value="PASS")
    s4 = step(None, "NUMBERED", "Thread Ring Go gauge", sort=4)
    step(s4, "TAKE", "Take Object Thread Ring Go gauge", d_go, 1)
    step(s4, "OPERATOR_DIALOG", "Thread Ring Go gauge result", None, 2, question="Thread ring GO gauge entered fully?",
         options="OK,NOT OK", ng_options="NOT OK", variable="THREAD_GO")
    step(s4, "PLACE", "Place Object Thread Ring Go gauge", d_go, 3)
    s5 = step(None, "NUMBERED", "Unload", sort=5)
    step(s5, "TAKE", "Take Object JOB LOADING", d_job, 1)
    J.release(job_id, ctx.session.user_id)
    ctx.audit("DEMO_SEEDED", "job", job_id, {})
    return job_id
