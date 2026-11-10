"""Password hashing (scrypt, stdlib), password policy and the RBAC session."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field


class Perm:
    RUN_INSPECTION = "RUN_INSPECTION"
    OVERRIDE_STEP = "OVERRIDE_STEP"
    VIEW_REPORTS = "VIEW_REPORTS"
    EXPORT_REPORTS = "EXPORT_REPORTS"
    EDIT_JOBS = "EDIT_JOBS"
    TEACH_DETECTIONS = "TEACH_DETECTIONS"
    RELEASE_JOBS = "RELEASE_JOBS"
    CALIBRATE = "CALIBRATE"
    MANAGE_HARDWARE = "MANAGE_HARDWARE"
    MANAGE_USERS = "MANAGE_USERS"
    VIEW_AUDIT = "VIEW_AUDIT"
    MANAGE_SETTINGS = "MANAGE_SETTINGS"
    MANAGE_PROCESSES = "MANAGE_PROCESSES"


class PermissionDenied(Exception):
    pass


_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def password_policy_errors(password: str, username: str = "") -> list[str]:
    errors = []
    if len(password) < 8:
        errors.append("be at least 8 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors.append("contain both letters and digits")
    if username and username.lower() in password.lower():
        errors.append("not contain the user name")
    return errors


@dataclass
class Session:
    user_id: int
    username: str
    full_name: str
    role_code: str
    permissions: set[str] = field(default_factory=set)

    def can(self, perm: str) -> bool:
        return perm in self.permissions

    def require(self, perm: str) -> None:
        if perm not in self.permissions:
            raise PermissionDenied(f"Your role ({self.role_code}) does not allow: {perm}")
