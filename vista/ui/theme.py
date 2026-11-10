"""Light theme. Structure from VS Code (title bar, command centre, status bar) and Arkite (tabs, trees,
Properties panel); one loud colour - the projector's signal amber - kept for live operator guidance."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

C = {
    "canvas": "#F2F4F7", "surface": "#FFFFFF", "chrome": "#E7EAEF", "ribbon": "#F8F9FB", "line": "#D6DBE2",
    "line2": "#E6E9EE", "text": "#18212C", "muted": "#5C6877", "faint": "#8A94A1", "ink": "#142B54",
    "primary": "#1F5FBF", "primary_hover": "#1A52A6", "primary_soft": "#E3ECFA", "hover": "#EDF1F7",
    "accent": "#E9A100", "accent_soft": "#FFF4D6", "ok": "#1F9D57", "ok_soft": "#E2F5EA", "ng": "#D33A3A",
    "ng_soft": "#FBE5E5", "warn": "#D97A1E", "warn_soft": "#FCEEDD", "info": "#1F5FBF",
    # aliases kept for code written against the previous theme
    "bg": "#F2F4F7", "panel": "#FFFFFF", "panel2": "#F6F7F9",
}
DISPLAY = "Bahnschrift"
BODY = "Segoe UI"


def font(size: int = 10, bold: bool = False, display: bool = False, weight: int | None = None) -> QFont:
    f = QFont(DISPLAY if display else BODY)
    f.setPointSize(size)
    if weight is not None:
        f.setWeight(QFont.Weight(weight))
    else:
        f.setBold(bold)
    return f


QSS = f"""
QWidget {{ color: {C['text']}; }}
QMainWindow, QDialog, QStackedWidget > QWidget#Page {{ background: {C['canvas']}; }}
QWidget#Page {{ background: {C['canvas']}; }}
QLabel {{ background: transparent; }}
QLabel#H1 {{ font-size: 17pt; font-weight: 600; color: {C['text']}; }}
QLabel#H2 {{ font-size: 11pt; font-weight: 600; color: {C['text']}; }}
QLabel#H3 {{ font-weight: 600; color: {C['text']}; }}
QLabel#Muted {{ color: {C['muted']}; }}
QLabel#Faint {{ color: {C['faint']}; font-size: 8pt; }}

/* ---------- title bar (VS Code) ---------- */
QFrame#TitleBar {{ background: {C['chrome']}; border-bottom: 1px solid {C['line']}; }}
QFrame#TitleBar QToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 3px 8px; }}
QFrame#TitleBar QToolButton:hover {{ background: #D9DEE6; }}
QFrame#TitleBar QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#WinBtn {{ border-radius: 0; padding: 0; min-width: 44px; min-height: 36px; }}
QToolButton#WinClose:hover {{ background: #E81123; }}
QPushButton#Command {{ background: #F6F7F9; border: 1px solid #C9D0D9; border-radius: 6px; padding: 3px 10px;
    text-align: left; color: {C['muted']}; }}
QPushButton#Command:hover {{ background: #FFFFFF; border-color: #AEB7C3; }}
QLabel#RoleChip {{ background: {C['primary']}; color: white; border-radius: 4px; padding: 2px 9px; font-weight: 600; }}

/* ---------- ribbon ---------- */
QFrame#Ribbon {{ background: {C['ribbon']}; border-bottom: 1px solid {C['line']}; }}
QToolButton#RibbonBtn {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px 6px 3px 6px;
    color: {C['text']}; min-width: 66px; }}
QToolButton#RibbonBtn:hover {{ background: {C['hover']}; border-color: {C['line2']}; }}
QToolButton#RibbonBtn:checked {{ background: {C['primary_soft']}; border-color: #BCD0F1; color: {C['primary']}; font-weight: 600; }}
QLabel#RibbonGroup {{ color: {C['faint']}; font-size: 7.5pt; }}
QFrame#RibbonSep {{ background: {C['line']}; max-width: 1px; min-width: 1px; margin: 6px 6px; }}

/* ---------- status bar ---------- */
QFrame#StatusBar {{ background: {C['chrome']}; border-top: 1px solid {C['line']}; }}
QFrame#StatusBar QLabel {{ font-size: 8.5pt; color: {C['muted']}; }}
QFrame#StatusBar QLabel#ChipOk, QLabel#ChipOk {{ background: {C['ok']}; color: white; padding: 1px 8px; font-size: 8.5pt; }}
QFrame#StatusBar QLabel#ChipNg, QLabel#ChipNg {{ background: {C['ng']}; color: white; padding: 1px 8px; font-size: 8.5pt; }}
QFrame#StatusBar QLabel#ChipWarn, QLabel#ChipWarn {{ background: {C['warn']}; color: white; padding: 1px 8px; font-size: 8.5pt; }}
QPushButton#ChipBtnOk, QPushButton#ChipBtnWarn, QPushButton#ChipBtnNg {{ border: none; border-radius: 0; color: white;
    padding: 1px 12px; font-size: 8.5pt; }}
QPushButton#ChipBtnOk {{ background: {C['ok']}; }} QPushButton#ChipBtnWarn {{ background: {C['warn']}; }}
QPushButton#ChipBtnNg {{ background: {C['ng']}; }}

/* ---------- surfaces ---------- */
QFrame#Panel {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 6px; }}
QFrame#Card {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 6px; }}
QFrame#Card:hover {{ border-color: #AFC3E4; }}
QFrame#CardSel {{ background: #F7FAFF; border: 1.5px solid {C['primary']}; border-radius: 6px; }}
QFrame#PropHeader {{ background: transparent; border-bottom: 1px solid {C['line']}; }}
QFrame#Toolbar {{ background: transparent; }}
QFrame#Hint {{ background: #F1F6FE; border: 1px solid #CFE0F7; border-radius: 4px; }}

/* ---------- inputs ---------- */
QPushButton {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 4px; padding: 5px 12px; }}
QPushButton:hover {{ background: {C['hover']}; border-color: #B9C2CE; }}
QPushButton:pressed {{ background: #E2E7EE; }}
QPushButton:disabled {{ color: #A3ACB8; background: #F4F5F7; }}
QPushButton[kind="primary"] {{ background: {C['primary']}; border: 1px solid {C['primary']}; color: white; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {C['primary_hover']}; }}
QPushButton[kind="primary"]:disabled {{ background: #9DB6DD; border-color: #9DB6DD; }}
QPushButton[kind="danger"] {{ color: {C['ng']}; border-color: #E9B4B4; }}
QPushButton[kind="danger"]:hover {{ background: {C['ng_soft']}; }}
QPushButton[kind="ok"] {{ background: {C['ok']}; border-color: {C['ok']}; color: white; font-weight: 600; }}
QPushButton[kind="big"] {{ font-size: 15pt; padding: 12px 22px; }}
QPushButton[kind="link"] {{ border: none; background: transparent; color: {C['primary']}; text-decoration: underline;
    padding: 0; text-align: left; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}
QToolButton#Tool {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 3px; }}
QToolButton#Tool:hover {{ background: {C['hover']}; border-color: {C['line2']}; }}
QToolButton#Tool:checked {{ background: {C['primary_soft']}; border-color: #BCD0F1; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit {{
    background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 4px; padding: 4px 6px;
    selection-background-color: {C['primary']}; selection-color: white; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
    border: 1px solid {C['primary']}; }}
QLineEdit:read-only {{ background: #F6F7F9; color: {C['muted']}; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {C['line']}; selection-background-color: {C['primary_soft']};
    selection-color: {C['text']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator {{ border: 1px solid #9AA5B3; border-radius: 3px; background: white; }}
QCheckBox::indicator:checked {{ background: {C['primary']}; border-color: {C['primary']}; }}

/* ---------- lists / trees / tables ---------- */
QTreeWidget, QTableWidget, QListWidget, QTreeView {{ background: {C['surface']}; border: 1px solid {C['line']};
    border-radius: 4px; alternate-background-color: #FAFBFC; gridline-color: {C['line2']}; outline: none; }}
QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:hover, QListWidget::item:hover, QTableWidget::item:hover {{ background: #F3F6FA; }}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{ background: {C['primary_soft']};
    color: {C['text']}; }}
QHeaderView::section {{ background: #F6F7F9; color: {C['muted']}; border: none; border-bottom: 1px solid {C['line']};
    border-right: 1px solid {C['line2']}; padding: 5px 6px; }}

/* ---------- tabs (Arkite page tabs) ---------- */
QTabWidget::pane {{ border: 1px solid {C['line']}; background: {C['surface']}; border-radius: 0 4px 4px 4px; top: -1px; }}
QTabBar::tab {{ background: #ECEFF3; color: {C['muted']}; border: 1px solid {C['line']}; border-bottom: none;
    padding: 5px 14px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
QTabBar::tab:selected {{ background: {C['surface']}; color: {C['text']}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: #F4F6F9; }}

QGroupBox {{ border: 1px solid {C['line']}; border-radius: 6px; margin-top: 14px; padding-top: 8px; background: white; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {C['muted']}; font-weight: 600; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C5CCD6; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #A9B3C0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C5CCD6; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {C['primary_soft']}; }}
QToolTip {{ background: #FFFFFF; color: {C['text']}; border: 1px solid {C['line']}; padding: 4px; }}
QProgressBar {{ background: #EEF1F5; border: none; border-radius: 3px; text-align: center; height: 10px; font-size: 8pt; }}
QProgressBar::chunk {{ background: {C['primary']}; border-radius: 3px; }}
QMenu {{ background: white; border: 1px solid {C['line']}; padding: 4px; }}
QMenu::item {{ padding: 5px 28px 5px 24px; border-radius: 3px; }}
QMenu::item:selected {{ background: {C['primary_soft']}; color: {C['text']}; }}
QMenu::item:disabled {{ color: #A3ACB8; }}
QMenu::separator {{ height: 1px; background: {C['line2']}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 6px; }}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    app.setFont(font(9))
    pal = QPalette()
    for role, key in ((QPalette.Window, "canvas"), (QPalette.Base, "surface"), (QPalette.AlternateBase, "panel2"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "primary"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "faint")):
        pal.setColor(role, QColor(C[key]))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
