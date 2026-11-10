"""Traceability exports.

`export_traceability_xlsx` produces one row per inspected part with one column per step name
(OK / NG / FORCED / value) and hyperlinks to the evidence images - the same layout as the
existing Arkite image/column report, without manual configuration.
"""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

FILL = {"PASS": "C6EFCE", "FAIL": "FFC7CE", "ABORTED": "FFEB9C", "OK": "C6EFCE", "NG": "FFC7CE", "FORCED": "FFEB9C"}


def _safe(v):
    """Strings beginning with = + - @ would be stored as formulas by openpyxl / Excel."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _local(dt):
    return dt.astimezone().replace(tzinfo=None) if dt else None


def export_traceability_xlsx(path: Path, runs: list[dict], step_rows: list[dict], station: str) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Traceability"
    by_run: dict = {}
    step_names: list[str] = []
    for r in step_rows:
        by_run.setdefault(r["run_id"], []).append(r)
        if r["step_name"] not in step_names and r["result"] != "SKIPPED":
            step_names.append(r["step_name"])
    head = ["Station", "Started", "Finished", "Barcode", "Job", "Revision", "Variant", "Operator", "Result",
            "Cycle (s)", "NG count", "Forced", "Remarks"] + [_safe(n) for n in step_names]
    ws.append(head)
    for c in range(1, len(head) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2B3541")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for run in runs:
        rows = by_run.get(run["id"], [])
        final = {}
        for sr in rows:                     # final result per step = last row (NG then OK after rework)
            final[sr["step_name"]] = sr
        line = [station, _local(run["started_at"]), _local(run["finished_at"]), run["barcode"], run["job_code"],
                run["job_revision"], run["variant_code"], run.get("operator"), run["result"],
                round((run["cycle_time_ms"] or 0) / 1000, 1), run["ng_count"], run["forced_count"], run["remarks"]]
        for n in step_names:
            sr = final.get(n)
            if sr is None:
                line.append("")
            elif sr["result"] == "INFO":
                line.append(sr["value"] or "OK")
            else:
                had_ng = any(x["step_name"] == n and x["result"] == "NG" for x in rows)
                line.append(sr["result"] + (" (rework)" if had_ng and sr["result"] == "OK" else ""))
        ws.append([_safe(v) for v in line])
        r_idx = ws.max_row
        ws.cell(row=r_idx, column=9).fill = PatternFill("solid", fgColor=FILL.get(run["result"], "FFFFFF"))
        for k, n in enumerate(step_names):
            sr = final.get(n)
            cell = ws.cell(row=r_idx, column=len(head) - len(step_names) + k + 1)
            if sr is not None:
                cell.fill = PatternFill("solid", fgColor=FILL.get(sr["result"], "FFFFFF"))
                if sr["evidence_path"]:
                    cell.hyperlink = Path(sr["evidence_path"]).resolve().as_uri()
                    cell.font = Font(underline="single", color="1F4E79")
    for c in range(1, len(head) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14 if c > 13 else [10, 18, 18, 18, 14, 9, 9, 12, 9, 9, 9, 8,
                                                                              30][c - 1]
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions
    det = wb.create_sheet("Step details")
    det.append(["Barcode", "Run", "Step", "Path", "Type", "Detection", "Started", "Duration (ms)", "Result",
                "Class", "Score", "Value", "Evidence"])
    barcode = {r["id"]: r["barcode"] for r in runs}
    for sr in step_rows:
        det.append([barcode.get(sr["run_id"]), str(sr["run_id"]), sr["step_name"], sr["step_path"], sr["step_type"],
                    sr["detection_name"], _local(sr["started_at"]), sr["duration_ms"], sr["result"], sr["qc_class"],
                    sr["score"], _safe(sr["value"]), sr["evidence_path"]])
    wb.save(path)
    return path


def export_csv(path: Path, rows: list[dict], columns: list[str]) -> Path:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for r in rows:
            out = []
            for c in columns:
                v = r.get(c)
                if hasattr(v, "astimezone"):
                    v = _local(v)
                if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
                    v = "'" + v          # CSV formula injection guard
                out.append(v)
            w.writerow(out)
    return path
