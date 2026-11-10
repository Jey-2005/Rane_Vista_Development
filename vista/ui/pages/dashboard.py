"""Dashboard: KPI tiles, output per hour/day, NG pareto, slowest steps and recent inspections."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCharts import (QBarCategoryAxis, QBarSet, QChart, QChartView, QHorizontalBarSeries,
                              QStackedBarSeries, QValueAxis)
from PySide6.QtCore import QMargins, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from vista.ui.theme import C
from vista.ui.widgets.common import KpiTile, Page, button, hrow, label

RES_COL = {"PASS": C["ok"], "FAIL": C["ng"], "ABORTED": C["warn"], "RUNNING": C["primary"]}


def _chart(title: str) -> QChart:
    ch = QChart()
    ch.setTitle(title)
    f = QFont()
    f.setPointSize(10)
    f.setBold(True)
    ch.setTitleFont(f)
    ch.setTitleBrush(QColor(C["text"]))
    ch.setBackgroundBrush(QColor("white"))
    ch.setBackgroundRoundness(0)
    ch.setMargins(QMargins(6, 6, 6, 6))
    ch.legend().setLabelColor(QColor(C["muted"]))
    ch.setAnimationOptions(QChart.NoAnimation)
    return ch


def _axis(ax) -> None:
    ax.setLabelsColor(QColor(C["muted"]))
    ax.setGridLineColor(QColor(C["line2"]))
    ax.setLinePenColor(QColor(C["line"]))


class DashboardPage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.period = QComboBox()
        self.period.addItems(["Today", "Last 7 days", "Last 30 days"])
        self.period.currentIndexChanged.connect(self.refresh)
        self.updated = label("", "Muted")
        title = label(f"Station performance · {ctx.cfg.station_code}", "H1")
        root.addLayout(hrow(title, None, self.updated, self.period, button("Refresh", None, self.refresh, ico="reset")))
        tiles = QHBoxLayout()
        self.t_total = KpiTile("Parts inspected", ico="cube", color=C["primary"])
        self.t_pass = KpiTile("Pass", color=C["ok"], ico="check_circle")
        self.t_fail = KpiTile("Fail", color=C["ng"], ico="x_circle")
        self.t_fpy = KpiTile("First-pass yield", color="#7A3DB8", ico="release")
        self.t_cycle = KpiTile("Average cycle (s)", color=C["warn"], ico="clock")
        for t in (self.t_total, self.t_pass, self.t_fail, self.t_fpy, self.t_cycle):
            tiles.addWidget(t)
        root.addLayout(tiles)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.v_out, self.v_ng, self.v_dur = QChartView(), QChartView(), QChartView()
        for v in (self.v_out, self.v_ng, self.v_dur):
            v.setRenderHint(QPainter.Antialiasing)
            v.setMinimumHeight(230)
            v.setStyleSheet(f"border: 1px solid {C['line']}; border-radius: 6px; background: white;")
        grid.addWidget(self.v_out, 0, 0, 1, 2)
        grid.addWidget(self.v_ng, 1, 0)
        grid.addWidget(self.v_dur, 1, 1)
        recent = QFrame()
        recent.setObjectName("Panel")
        rl = QVBoxLayout(recent)
        rl.setContentsMargins(10, 8, 10, 10)
        rl.addWidget(label("Recent inspections", "H2"))
        self.recent = QTableWidget(0, 5)
        self.recent.setHorizontalHeaderLabels(["Time", "Barcode", "Job", "Result", "Cycle s"])
        self.recent.verticalHeader().setVisible(False)
        self.recent.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent.horizontalHeader().setStretchLastSection(True)
        self.recent.setStyleSheet("QTableWidget { border: none; }")
        rl.addWidget(self.recent)
        rl.addWidget(label("Full traceability with evidence images: File > Export inspection data (Ctrl+E).", "Faint"))
        grid.addWidget(recent, 0, 2, 2, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 2)
        root.addLayout(grid, 1)
        self._t = QTimer(self)
        self._t.timeout.connect(self.refresh)

    def on_show(self) -> None:
        self.refresh()
        self._t.start(60_000)

    def on_hide(self) -> None:
        self._t.stop()

    def _since(self) -> datetime:
        start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return start - timedelta(days={0: 0, 1: 6, 2: 29}[self.period.currentIndex()])

    def refresh(self) -> None:
        since = self._since()
        k = self.ctx.runs.kpis(since)
        total = k["total"] or 0
        self.t_total.set(str(total))
        self.t_pass.set(str(k["pass"] or 0))
        self.t_fail.set(str(k["fail"] or 0))
        self.t_fpy.set(f"{100 * (k['first_pass'] or 0) / total:.1f}%" if total else "-")
        self.t_cycle.set(f"{(k['avg_cycle_ms'] or 0) / 1000:.1f}" if k["avg_cycle_ms"] else "-")
        self._set(self.v_out, self._output(since))
        self._set(self.v_ng, self._bars("NG by step", [(r["step_name"], r["n"])
                                                       for r in self.ctx.runs.ng_pareto(since, 8)], C["ng"]))
        self._set(self.v_dur, self._bars("Slowest steps (average s)",
                                         [(r["step_name"], round(float(r["avg_ms"]) / 1000, 1))
                                          for r in self.ctx.runs.step_durations(since, 8)], C["primary"]))
        runs = self.ctx.runs.search(since, datetime.now().astimezone() + timedelta(minutes=1), limit=25)
        t = self.recent
        t.setRowCount(len(runs))
        for i, r in enumerate(runs):
            vals = [f"{r['started_at'].astimezone():%d-%m %H:%M}", r["barcode"] or "-", r["job_code"], r["result"],
                    f"{(r['cycle_time_ms'] or 0) / 1000:.1f}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 3:
                    it.setForeground(QColor(RES_COL.get(v, C["text"])))
                t.setItem(i, c, it)
        t.resizeColumnsToContents()
        self.updated.setText(f"updated {datetime.now():%H:%M}")

    @staticmethod
    def _set(view: QChartView, chart: QChart) -> None:
        old = view.chart()
        view.setChart(chart)
        if old is not None:
            old.deleteLater()

    def _output(self, since: datetime) -> QChart:
        daily = self.period.currentIndex() > 0
        ch = _chart("Output per day" if daily else "Output per hour")
        agg: dict[str, list[int]] = {}
        for r in self.ctx.runs.hourly(since):
            key = f"{r['hour'].astimezone():%d-%m}" if daily else f"{r['hour'].astimezone():%H}:00"
            a = agg.setdefault(key, [0, 0])
            a[0] += r["pass"]
            a[1] += r["fail"]
        sp, sf = QBarSet("Pass"), QBarSet("Fail")
        sp.setColor(QColor(C["ok"]))
        sf.setColor(QColor(C["ng"]))
        for v in agg.values():
            sp.append(v[0])
            sf.append(v[1])
        s = QStackedBarSeries()
        s.append(sp)
        s.append(sf)
        s.setBarWidth(0.55)
        ch.addSeries(s)
        ax = QBarCategoryAxis()
        ax.append(list(agg.keys()) or ["-"])
        ay = QValueAxis()
        ay.setLabelFormat("%d")
        ay.setRange(0, max([sum(v) for v in agg.values()] + [5]))
        for a in (ax, ay):
            _axis(a)
        ch.addAxis(ax, Qt.AlignBottom)
        ch.addAxis(ay, Qt.AlignLeft)
        s.attachAxis(ax)
        s.attachAxis(ay)
        return ch

    def _bars(self, title: str, data: list, color: str) -> QChart:
        ch = _chart(title)
        data = list(reversed(data))
        bs = QBarSet("")
        bs.setColor(QColor(color))
        for _, v in data:
            bs.append(float(v))
        s = QHorizontalBarSeries()
        s.append(bs)
        s.setBarWidth(0.6)
        ch.addSeries(s)
        ch.legend().hide()
        ay = QBarCategoryAxis()
        ay.append([n[:26] for n, _ in data] or ["no data yet"])
        ax = QValueAxis()
        ax.setRange(0, max([v for _, v in data] + [1]) * 1.15)
        for a in (ax, ay):
            _axis(a)
        ch.addAxis(ay, Qt.AlignLeft)
        ch.addAxis(ax, Qt.AlignBottom)
        s.attachAxis(ax)
        s.attachAxis(ay)
        return ch
