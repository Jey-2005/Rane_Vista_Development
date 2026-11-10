"""Regression test: a keyboard-wedge scan must arrive exactly once per character (real Qt key path)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget  # noqa: E402

from vista.hardware.barcode_scanner import KeyboardWedgeFilter  # noqa: E402


def test_scan_not_doubled():
    app = QApplication.instance() or QApplication([])
    wedge = KeyboardWedgeFilter()
    got = []
    wedge.scanned.connect(got.append)
    app.installEventFilter(wedge)
    w = QWidget()
    le = QLineEdit(w)
    w.show()
    le.setFocus()
    app.processEvents()
    for ch in "LH123456":
        QTest.keyClick(w.windowHandle(), ch)     # same route as a physical keyboard / USB scanner
    QTest.keyClick(w.windowHandle(), Qt.Key_Return)
    app.processEvents()
    assert got == ["LH123456"], got
    app.removeEventFilter(wedge)


if __name__ == "__main__":
    test_scan_not_doubled()
    print("WEDGE OK")
