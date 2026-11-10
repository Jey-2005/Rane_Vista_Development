"""Sign-in, first administrator, change password and supervisor re-authentication dialogs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from vista import __version__
from vista.app_context import AuthError
from vista.core.config import resource_dir
from vista.ui.icons import icon
from vista.ui.theme import C, font
from vista.ui.widgets.common import button, hrow, label


class _Base(QDialog):
    """Two-panel dialog: navy brand panel on the left, form on the right."""

    def __init__(self, title: str, subtitle: str = "", station: str = ""):
        super().__init__()
        self.setWindowTitle(f"RANE VISTA - {title}")
        self.setMinimumWidth(760)
        self.setStyleSheet(f"QDialog {{ background: {C['surface']}; }}")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        brand = QFrame()
        brand.setFixedWidth(280)
        brand.setStyleSheet(f"QFrame {{ background: {C['ink']}; }} QLabel {{ color: #DCE6F5; }}")
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(28, 32, 28, 24)
        logo = QLabel()
        png = resource_dir() / "assets" / "rane_vista.png"
        if png.exists():
            logo.setPixmap(QPixmap(str(png)).scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        bl.addWidget(logo)
        name = QLabel("RANE VISTA")
        name.setFont(font(22, display=True))
        name.setStyleSheet("color: white;")
        bl.addWidget(name)
        tag = QLabel("Visual Inspection &\nSmart Task Assistance")
        tag.setStyleSheet(f"color: {C['accent']}; font-size: 10pt;")
        bl.addWidget(tag)
        bl.addStretch(1)
        if station:
            st = QLabel(f"Station\n{station}")
            st.setFont(font(12, display=True))
            bl.addWidget(st)
        bl.addWidget(QLabel(f"Version {__version__}"))
        root.addWidget(brand)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(36, 36, 36, 28)
        self.lay.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("H1")
        self.lay.addWidget(t)
        if subtitle:
            self.lay.addWidget(label(subtitle, "Muted", wrap=True))
        self.lay.addSpacing(8)
        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet(f"color: {C['ng']}; background: {C['ng_soft']}; border-radius: 4px; padding: 6px 8px;")
        self.err.hide()
        root.addWidget(body, 1)

    def field(self, caption: str, w: QWidget) -> QWidget:
        self.lay.addWidget(label(caption, "H3"))
        w.setMinimumHeight(32)
        self.lay.addWidget(w)
        return w

    def finish(self, *buttons) -> None:
        self.lay.addWidget(self.err)
        self.lay.addStretch(1)
        self.lay.addLayout(hrow(None, *buttons))

    def fail(self, msg: str) -> None:
        self.err.setText(msg)
        self.err.show()

    @staticmethod
    def pw() -> QLineEdit:
        e = QLineEdit()
        e.setEchoMode(QLineEdit.Password)
        return e


class LoginDialog(_Base):
    def __init__(self, ctx):
        super().__init__("Sign in", "Use your user name or employee code.", ctx.cfg.station_code)
        self.ctx = ctx
        self.user = self.field("User", QLineEdit())
        self.user.addAction(icon("user", C["faint"], 16), QLineEdit.LeadingPosition)
        self.password = self.field("Password", self.pw())
        self.password.addAction(icon("lock", C["faint"], 16), QLineEdit.LeadingPosition)
        ok = button("Sign in", "primary", self.accept_login)
        ok.setDefault(True)
        ok.setMinimumWidth(120)
        self.finish(button("Exit", None, self.reject), ok)
        self.user.setFocus()

    def accept_login(self) -> None:
        try:
            self.ctx.login(self.user.text(), self.password.text())
        except AuthError as exc:
            self.password.clear()
            return self.fail(str(exc))
        except Exception as exc:
            return self.fail(f"Sign-in failed: {exc}")
        self.accept()


class FirstAdminDialog(_Base):
    def __init__(self, ctx):
        super().__init__("Create the administrator",
                         "No users exist yet. Create the first administrator for this installation - there is no "
                         "default password.", ctx.cfg.station_code)
        self.ctx = ctx
        self.user = self.field("User name", QLineEdit())
        self.name = self.field("Full name", QLineEdit())
        self.p1 = self.field("Password", self.pw())
        self.p2 = self.field("Repeat password", self.pw())
        self.finish(button("Cancel", None, self.reject), button("Create administrator", "primary", self.create))

    def create(self) -> None:
        if not self.user.text().strip() or not self.name.text().strip():
            return self.fail("User name and full name are required.")
        if self.p1.text() != self.p2.text():
            return self.fail("Passwords do not match.")
        try:
            self.ctx.create_first_admin(self.user.text().strip(), self.name.text().strip(), self.p1.text())
        except AuthError as exc:
            return self.fail(str(exc))
        self.accept()


class ChangePasswordDialog(_Base):
    def __init__(self, ctx, forced: bool = False):
        super().__init__("Change password", "Your password must be changed before continuing." if forced else
                         "At least 8 characters with letters and digits.", ctx.cfg.station_code)
        self.ctx = ctx
        self.old = self.field("Current password", self.pw())
        self.p1 = self.field("New password", self.pw())
        self.p2 = self.field("Repeat new password", self.pw())
        self.finish(button("Cancel", None, self.reject), button("Change password", "primary", self.change))

    def change(self) -> None:
        if self.p1.text() != self.p2.text():
            return self.fail("New passwords do not match.")
        try:
            self.ctx.change_password(self.old.text(), self.p1.text())
        except AuthError as exc:
            return self.fail(str(exc))
        self.accept()


class ReauthDialog(_Base):
    def __init__(self, ctx, perm: str, reason: str):
        super().__init__("Authorisation required", reason, ctx.cfg.station_code)
        self.ctx, self.perm, self.session = ctx, perm, None
        self.user = self.field("Supervisor", QLineEdit())
        self.password = self.field("Password", self.pw())
        self.finish(button("Cancel", None, self.reject), button("Authorise", "primary", self.ok))

    def ok(self) -> None:
        try:
            self.session = self.ctx.check_credentials(self.user.text(), self.password.text(), self.perm)
        except AuthError as exc:
            self.password.clear()
            return self.fail(str(exc))
        self.accept()


def authorise(parent, ctx, perm: str, reason: str):
    if ctx.session and ctx.session.can(perm):
        return ctx.session
    dlg = ReauthDialog(ctx, perm, reason)
    dlg.setParent(parent, Qt.Dialog)
    return dlg.session if dlg.exec() == QDialog.Accepted else None
