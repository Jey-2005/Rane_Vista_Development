"""Users page: user list with avatars and role chips | Properties (inline edit); roles & permissions matrix."""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLineEdit,
                               QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout)

from vista.core.security import PermissionDenied, Perm, hash_password
from vista.ui.theme import C
from vista.ui.widgets.common import Page, PropertiesPanel, SearchBox, button, confirm, error, hrow, info, label

ROLE_COL = {"ADMIN": "#7A3DB8", "QUALITY": "#1F9D57", "ENGINEER": "#1F5FBF", "SUPERVISOR": "#D97A1E",
            "OPERATOR": "#5C6877"}


def temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        p = "".join(secrets.choice(alphabet) for _ in range(10))
        if any(c.isdigit() for c in p) and any(c.isalpha() for c in p):
            return p


def avatar(name: str, color: str, size: int = 30) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size * 2, size * 2)
    p.setPen(QColor("white"))
    f = p.font()
    f.setPixelSize(int(size * 0.8))
    f.setBold(True)
    p.setFont(f)
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    p.drawText(pm.rect(), Qt.AlignCenter, initials)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


class UsersPage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.users: list[dict] = []
        self.sel: dict | None = None
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        left = QFrame()
        left.setObjectName("Panel")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        self.search = SearchBox("Search users")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._fill)
        ll.addLayout(hrow(button("New user", "primary", self.new, ico="plus"), None, self.search))
        tabs = QTabWidget()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["User", "Employee code", "Role", "Stations", "Status", "Last sign-in"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setIconSize(QSize(28, 28))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(lambda r, *_: self._select(r))
        tabs.addTab(self.table, "Users")
        self.matrix = QTableWidget()
        self.matrix.verticalHeader().setVisible(False)
        self.matrix.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabs.addTab(self.matrix, "Roles and permissions")
        ll.addWidget(tabs, 1)
        root.addWidget(left, 1)
        self.props = PropertiesPanel()
        root.addWidget(self.props)

    def on_show(self) -> None:
        try:
            self.ctx.require(Perm.MANAGE_USERS)
        except PermissionDenied:
            return
        self.users = self.ctx.users.list()
        self._fill(self.search.text())
        roles, perms, pairs = self.ctx.users.permission_matrix()
        m = self.matrix
        m.setColumnCount(len(roles) + 1)
        m.setHorizontalHeaderLabels(["Permission"] + [r["name"] for r in roles])
        m.setRowCount(len(perms))
        for i, p in enumerate(perms):
            m.setItem(i, 0, QTableWidgetItem(p["description"]))
            for j, r in enumerate(roles):
                it = QTableWidgetItem("✓" if (r["code"], p["code"]) in pairs else "")
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor(C["ok"]))
                m.setItem(i, j + 1, it)
        m.resizeColumnsToContents()

    def _fill(self, text: str = "") -> None:
        t = text.lower().strip()
        rows = [u for u in self.users if not t or t in u["username"].lower() or t in u["full_name"].lower()
                or t in (u["employee_code"] or "").lower()]
        self.visible = rows
        tb = self.table
        tb.setRowCount(len(rows))
        now = datetime.now(timezone.utc)
        for i, u in enumerate(rows):
            status = "Disabled" if not u["is_active"] else (
                "Locked" if u["locked_until"] and u["locked_until"] > now else "Active")
            first = QTableWidgetItem(avatar(u["full_name"], ROLE_COL.get(u["role_code"], C["muted"])),
                                     f"{u['full_name']}\n{u['username']}")
            tb.setItem(i, 0, first)
            tb.setItem(i, 1, QTableWidgetItem(u["employee_code"] or ""))
            r = QTableWidgetItem(u["role_code"].title())
            r.setForeground(QColor(ROLE_COL.get(u["role_code"], C["muted"])))
            tb.setItem(i, 2, r)
            tb.setItem(i, 3, QTableWidgetItem("All" if u["all_stations"] or u["role_code"] == "ADMIN"
                                              else ", ".join(u["stations"])))
            st = QTableWidgetItem(status)
            st.setForeground(QColor({"Active": C["ok"], "Locked": C["warn"]}.get(status, C["faint"])))
            tb.setItem(i, 4, st)
            tb.setItem(i, 5, QTableWidgetItem(f"{u['last_login_at'].astimezone():%d-%m-%Y %H:%M}"
                                              if u["last_login_at"] else "never"))
        tb.setColumnWidth(0, 240)
        tb.resizeColumnToContents(1)
        if rows:
            tb.setCurrentCell(0, 0)
        else:
            self._select(-1)

    def _select(self, row: int) -> None:
        self.sel = self.visible[row] if 0 <= row < len(getattr(self, "visible", [])) else None
        p = self.props
        p.clear()
        u = self.sel
        if u is None:
            p.heading("User", "Select a user.")
            p.end()
            return
        p.heading("User", f"{u['username']} · ID {u['id']}")
        self.f_name = p.field("Full name", QLineEdit(u["full_name"]))
        self.f_emp = p.field("Employee code (badge)", QLineEdit(u["employee_code"] or ""))
        self.f_role = QComboBox()
        for r in self.ctx.users.roles():
            self.f_role.addItem(r["name"], r["code"])
        self.f_role.setCurrentIndex(self.f_role.findData(u["role_code"]))
        p.field("Role", self.f_role)
        self.f_active = QCheckBox("Account active")
        self.f_active.setChecked(u["is_active"])
        self.f_all = QCheckBox("Access to all stations")
        self.f_all.setChecked(u["all_stations"])
        p.body.addWidget(self.f_active)
        p.body.addWidget(self.f_all)
        self.f_st = QListWidget()
        self.f_st.setFixedHeight(110)
        for s in self.ctx.stations.list():
            it = QListWidgetItem(f"{s['code']}  {s['name']}")
            it.setData(Qt.UserRole, s["id"])
            it.setCheckState(Qt.Checked if s["code"] in u["stations"] else Qt.Unchecked)
            self.f_st.addItem(it)
        p.field("Stations", self.f_st)
        perms = sorted(self.ctx.users.permissions(u["role_code"]))
        p.heading("Role grants")
        p.body.addWidget(label(", ".join(x.replace("_", " ").lower() for x in perms), "Muted", wrap=True))
        p.end()
        p.footer.addWidget(button("Reset password", None, self.reset_pw, ico="key"))
        p.footer.addWidget(button("Unlock", None, self.unlock, ico="lock"))
        p.footer.addStretch(1)
        p.footer.addWidget(button("Save", "primary", self.save, ico="save"))

    def _guard(self):
        try:
            return self.ctx.require(Perm.MANAGE_USERS)
        except PermissionDenied as exc:
            error(self, str(exc))
            return None

    def new(self) -> None:
        s = self._guard()
        if not s:
            return
        user, ok = QInputDialog.getText(self, "New user", "User name:")
        if not ok or not user.strip():
            return
        name, ok = QInputDialog.getText(self, "New user", "Full name:")
        if not ok or not name.strip():
            return
        roles = self.ctx.users.roles()
        role, ok = QInputDialog.getItem(self, "New user", "Role:", [r["name"] for r in roles],
                                        len(roles) - 1, False)
        if not ok:
            return
        code = roles[[r["name"] for r in roles].index(role)]["code"]
        pw = temp_password()
        try:
            uid = self.ctx.users.create(user.strip(), name.strip(), None, code, hash_password(pw), False, s.user_id)
            self.ctx.users.set_stations(uid, [self.ctx.station["id"]])
        except Exception as exc:
            return error(self, f"Could not create the user (name already used?): {exc}")
        self.ctx.audit("USER_CREATED", "user", uid, {"username": user, "role": code})
        info(self, f"User created with access to this station.\n\nTemporary password (shown once, must be changed "
                   f"at first sign-in):\n\n{pw}")
        self.on_show()

    def save(self) -> None:
        s, u = self._guard(), self.sel
        if not s or not u:
            return
        role = self.f_role.currentData()
        if u["id"] == s.user_id and u["role_code"] == "ADMIN" and (role != "ADMIN" or not self.f_active.isChecked()):
            return error(self, "You cannot demote or deactivate your own administrator account.")
        try:
            self.ctx.users.update(u["id"], self.f_name.text().strip(), self.f_emp.text().strip(), role,
                                  self.f_active.isChecked(), self.f_all.isChecked())
            self.ctx.users.set_stations(u["id"], [self.f_st.item(i).data(Qt.UserRole) for i in range(self.f_st.count())
                                                  if self.f_st.item(i).checkState() == Qt.Checked])
        except Exception as exc:
            return error(self, f"Save failed (employee code already used?): {exc}")
        self.ctx.audit("USER_UPDATED", "user", u["id"], {"role": role, "active": self.f_active.isChecked()})
        self.on_show()

    def reset_pw(self) -> None:
        u = self.sel
        if not u or not self._guard() or not confirm(self, f"Reset the password of {u['username']}?"):
            return
        pw = temp_password()
        self.ctx.users.set_password(u["id"], hash_password(pw), must_change=True)
        self.ctx.audit("PASSWORD_RESET", "user", u["id"], {})
        info(self, f"Temporary password for {u['username']} (shown once):\n\n{pw}")

    def unlock(self) -> None:
        if self.sel and self._guard():
            self.ctx.users.unlock(self.sel["id"])
            self.ctx.audit("USER_UNLOCKED", "user", self.sel["id"], {})
            self.on_show()
