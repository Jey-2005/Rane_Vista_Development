"""Step type catalogue (the subset of Arkite step types that the inspection module needs).

Each spec defines: label, whether it is a container, which detection types it accepts and the
editable parameters (key, label, kind, default, options).  kind: int|float|bool|str|choice|text
"""
from __future__ import annotations

CONTAINERS = ("NUMBERED", "COMPOSITE")

STEP_SPECS: dict[str, dict] = {
    "NUMBERED": {"label": "Numbered step", "container": True, "detection": None,
                 "help": "Logical operation shown to the operator as a numbered step; children run in order.",
                 "params": []},
    "COMPOSITE": {"label": "Composite step", "container": True, "detection": None,
                  "help": "Group of child steps executed in sequence or in any order, optionally repeated.",
                  "params": [("order", "Child order", "choice", "SEQUENTIAL", ["SEQUENTIAL", "ANY_ORDER"]),
                             ("repeat", "Repeat count", "int", 1, (1, 100))]},
    "PLACE": {"label": "Place object", "container": False, "detection": ("OBJECT",),
              "help": "Completes when the object is detected in its zone.",
              "params": [("timeout_s", "Warn after (s, 0 = never)", "int", 0, (0, 3600))]},
    "TAKE": {"label": "Take object", "container": False, "detection": ("OBJECT",),
             "help": "Completes when the object has been removed from its zone.",
             "params": [("timeout_s", "Warn after (s, 0 = never)", "int", 0, (0, 3600))]},
    "ACTIVITY": {"label": "Activity", "container": False, "detection": ("ACTIVITY",),
                 "help": "Completes when the operator performs the activity in the zone.",
                 "params": [("count", "Required repetitions", "int", 1, (1, 50)),
                            ("timeout_s", "Warn after (s, 0 = never)", "int", 0, (0, 3600))]},
    "PRESS": {"label": "Press virtual button", "container": False, "detection": ("BUTTON",),
              "help": "Completes when the projected button is pressed.", "params": []},
    "QUALITY_CHECK": {"label": "Quality check", "container": False, "detection": ("QUALITY",),
                      "help": "Vision check against taught classes. Choose what happens on a bad result.",
                      "params": [("on_fail", "On bad / missing result", "choice", "REWORK",
                                  ["REWORK", "FAIL_RUN", "ASK_SUPERVISOR"]),
                                 ("save_evidence", "Save evidence image", "bool", True, None),
                                 ("timeout_s", "Warn after (s, 0 = never)", "int", 0, (0, 3600))]},
    "WAIT_BARCODE": {"label": "Scan barcode", "container": False, "detection": None,
                     "help": "Waits for a scan. Can select the job variant from the barcode pattern.",
                     "params": [("variable", "Store in variable", "str", "BARCODE", None),
                                ("select_variant", "Select variant from barcode", "bool", True, None),
                                ("regex", "Accept only (regex, empty = any)", "str", "", None),
                                ("duplicate_policy", "Already passed barcode", "choice", "STATION_DEFAULT",
                                 ["STATION_DEFAULT", "BLOCK", "WARN", "ALLOW"])]},
    "SNAPSHOT": {"label": "Snapshot", "container": False, "detection": None,
                 "help": "Stores an evidence image of the bench for traceability.",
                 "params": [("source", "Camera", "choice", "COLOR", ["COLOR", "VISION", "IR"])]},
    "SET_VARIABLE": {"label": "Set variable", "container": False, "detection": None,
                     "help": "Sets a variable; {{NAME}} inserts another variable. Optionally logged as a result.",
                     "params": [("variable", "Variable", "str", "RESULT", None),
                                ("value", "Value", "str", "PASS", None),
                                ("record", "Record in traceability", "bool", True, None)]},
    "DELAY": {"label": "Delay", "container": False, "detection": None, "help": "Waits a fixed time.",
              "params": [("ms", "Duration (ms)", "int", 1000, (0, 600000))]},
    "OPERATOR_DIALOG": {"label": "Operator decision", "container": False, "detection": None,
                        "help": "Asks the operator to choose (e.g. gauge OK / NOT OK). NG options fail the part.",
                        "params": [("question", "Question", "str", "Gauge result?", None),
                                   ("options", "Options (comma separated)", "str", "OK,NOT OK", None),
                                   ("ng_options", "Options that mean NG", "str", "NOT OK", None),
                                   ("variable", "Store answer in variable", "str", "", None)]},
    "WORK_INSTRUCTION": {"label": "Work instruction", "container": False, "detection": None,
                         "help": "Shows the instruction until the operator confirms on screen.", "params": []},
}

LEAF_TYPES = tuple(k for k, v in STEP_SPECS.items() if not v["container"])


def default_params(step_type: str) -> dict:
    return {key: default for key, _, _, default, _ in STEP_SPECS[step_type]["params"]}


def default_name(step_type: str, detection_name: str | None = None) -> str:
    verb = {"PLACE": "Place", "TAKE": "Take", "ACTIVITY": "Activity", "PRESS": "Press",
            "QUALITY_CHECK": "Check"}.get(step_type)
    if verb and detection_name:
        return f"{verb} {detection_name}"
    return STEP_SPECS[step_type]["label"]


def operator_text(step: dict) -> str:
    """Instruction shown/projected for a leaf step when no custom instruction is set."""
    if step.get("instruction"):
        return step["instruction"]
    d = step.get("detection_name") or ""
    t = step["step_type"]
    p = step.get("params") or {}
    return {
        "PLACE": f"Place {d}", "TAKE": f"Take {d}", "ACTIVITY": f"Perform {d}", "PRESS": f"Press {d}",
        "QUALITY_CHECK": f"Check {d}", "WAIT_BARCODE": "Scan the part barcode", "SNAPSHOT": "Capturing image",
        "DELAY": "Please wait", "OPERATOR_DIALOG": p.get("question", "Choose"), "WORK_INSTRUCTION": step["name"],
        "SET_VARIABLE": step["name"],
    }.get(t, step["name"])
