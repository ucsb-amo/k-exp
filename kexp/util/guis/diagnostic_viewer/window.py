"""Diagnostic viewer: the per-shot diagnostic camera frames, live from liveOD.

Shows the MOT, GM and 2D-MOT fluorescence frames, and for every diagnostic
frame (those plus the MOT / GM beam frames on the xy and z Baslers) the mean
count of the latest shot and of the run so far, against a saved reference.

Where the numbers come from: liveOD broadcasts an AUX_NOTICE for every
PUT_DATA (no arrays); the viewer then asks liveOD for the latest frame of
each announced key (GET_AUX_DATA) with its ``<key>_meta`` record. Means are
over the frame as the run stores it (the DiagnosticCamera ROI), in DN, raw --
nothing subtracted. A frame is compared with a reference only when it was
taken at the reference's exposure and gain. A frame liveOD never received
(a placeholder camera, a dropped frame) is shown as missing, never as zero.

Receive-only on the broadcast; GET_AUX_DATA is the only request it sends.

    python -m kexp.util.guis.diagnostic_viewer
"""
from __future__ import annotations

import math
import sys
import threading
import time
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget,
)

from waxx.util.dashboard import theme

from .fetch import AuxFetcher, discover_endpoint
from .frames import FRAME_KEYS, FRAMES, SPEC, STATS, FrameHistory, configured_keys, \
    frame_stats, run_summary, same_settings, stat_value
from .references import ReferenceStore, build_reference, compare, reference_stat


def default_reference_path():
    try:
        from kexp.config.ip import DIAGNOSTIC_REFERENCE_CSV_PATH  # noqa: PLC0415
        return DIAGNOSTIC_REFERENCE_CSV_PATH
    except Exception:
        return None


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def _fin(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def fmt_dn(v, digits=1):
    return f"{v:.{digits}f}" if _fin(v) else "—"


def fmt_count(v, stat):
    """A count in DN: a mean to 0.1, a total to 4 significant figures (k / M / G)."""
    if not _fin(v):
        return "—"
    if stat == "mean":
        return f"{v:.1f}"
    for div, suffix in ((1e9, " G"), (1e6, " M"), (1e3, " k")):
        if abs(v) >= div:
            return f"{v / div:.4g}{suffix}"
    return f"{v:.4g}"


def fmt_settings(exposure, gain):
    if not _fin(exposure):
        return "not recorded"
    e = f"{exposure * 1e6:.0f} µs" if exposure < 1e-3 else f"{exposure * 1e3:.3g} ms"
    g = f"{gain:.3g} dB" if _fin(gain) else "? dB"
    return f"{e} / {g}"


def fmt_compare(c):
    if "reason" in c:
        return "—", c["reason"]
    d = c["delta_frac"]
    text = f"{d * 100:+.1f} %" if _fin(d) else "—"
    if _fin(c.get("z")):
        text += f"  ({c['z']:+.1f} σ)"
    return text, "σ = standard deviation of the reference's per-shot values"


def fmt_index(index):
    return "(" + ", ".join(str(i) for i in index) + ")" if index else "()"


# ---------------------------------------------------------------------------
# widgets
# ---------------------------------------------------------------------------

class FrameImage(QWidget):
    """One fluorescence frame with its caption."""

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.title = QLabel(f"<b>{spec.label}</b> <span style='color:{theme.FG_MUTED}'>"
                            f"{spec.camera} · {spec.key}</span>")
        self.caption = QLabel("no frame yet")
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet(f"color: {theme.FG_MUTED};")
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setMinimumSize(180, 160)
        vb = self.glw.addViewBox(lockAspect=True, invertY=True)
        vb.setMenuEnabled(False)
        self.img = pg.ImageItem(axisOrder="row-major")
        self.img.setColorMap(pg.colormap.get("viridis"))
        vb.addItem(self.img)
        self.vb = vb
        lay.addWidget(self.title)
        lay.addWidget(self.glw, 1)
        lay.addWidget(self.caption)

    def show_frame(self, arr, caption):
        a = np.asarray(arr)
        if a.ndim == 2 and a.size > 1:
            self.img.setImage(a, autoLevels=True)
            self.vb.autoRange(padding=0)
        self.caption.setText(caption)


class Section(QWidget):
    """A titled block whose content folds away under its header's arrow. The
    header keeps a one-line summary, so it says something while folded."""

    toggled = pyqtSignal(bool)

    def __init__(self, title, content, expanded=True, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        head = QHBoxLayout()
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.button.toggled.connect(self.set_expanded)
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color: {theme.FG_MUTED};")
        head.addWidget(self.button)
        head.addWidget(self.summary, 1)
        lay.addLayout(head)
        self.content = content
        lay.addWidget(content, 1)
        self.set_expanded(expanded)

    def set_expanded(self, on):
        on = bool(on)
        self.button.blockSignals(True)
        self.button.setChecked(on)
        self.button.blockSignals(False)
        self.button.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.content.setVisible(on)
        self.toggled.emit(on)

    def expanded(self):
        return self.button.isChecked()


class _Bg(QObject):
    done = pyqtSignal(object, object, object)       # callback, result, exception


class DiagnosticViewer(QWidget):
    """The viewer. ``start=False`` builds it without any network (tests)."""

    _endpoint_found = pyqtSignal(str, int)

    COLS = ("Frame", "Camera", "Quantity", "Shot (DN)", "Run mean ± sem (DN)",
            "Reference (DN)", "Δ shot", "Δ run", "Exposure / gain", "Notes")
    STAT_COL = 2

    def __init__(self, reference_csv_path="default", start=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnostic Viewer")
        path = default_reference_path() if reference_csv_path == "default" else reference_csv_path
        self.store = ReferenceStore(path)
        self.history = FrameHistory()
        self.reference = None
        self.run_id = None
        self.run_done = False
        self.run_state = ""
        self.shot_text = ""
        self.configured = configured_keys()
        self._shown = {}            # key -> (run_id, index, seq) on screen
        self.subscriber = None
        self.fetcher = None
        self._closing = False
        self._bg = _Bg()
        self._bg.done.connect(self._on_bg_done)
        self._build_ui()
        self._endpoint_found.connect(self._start_subscriber)
        self._refresh_table()
        if start:
            self.start()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        bar = QHBoxLayout()
        self.run_label = QLabel("Run —")
        self.run_label.setStyleSheet("font-weight: bold;")
        self.conn_label = QLabel("searching for liveOD…")
        self.conn_label.setStyleSheet(f"color: {theme.FG_MUTED};")
        bar.addWidget(self.run_label)
        bar.addSpacing(12)
        bar.addWidget(self.conn_label, 1)

        self.ref_label = QLabel("reference: none loaded")
        self.ref_label.setStyleSheet(f"color: {theme.FG_MUTED};")
        bar.addWidget(self.ref_label)
        bar.addWidget(QLabel("window"))
        self.window_spin = QSpinBox()
        self.window_spin.setRange(2, 1000)
        self.window_spin.setValue(20)
        self.window_spin.setSuffix(" shots")
        self.window_spin.setToolTip("Set takes the mean of each frame's last N shots")
        bar.addWidget(self.window_spin)
        self.ref_button = QToolButton()
        self.ref_button.setText("Reference ▾")
        self.ref_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.ref_button)
        menu.addAction("Set from the last N shots", self.set_reference)
        menu.addAction("Load…", self.open_load_dialog)
        menu.addAction("Clear", self.clear_reference)
        self.ref_button.setMenu(menu)
        bar.addWidget(self.ref_button)
        root.addLayout(bar)

        images = QWidget()
        il = QHBoxLayout(images)
        il.setContentsMargins(0, 0, 0, 0)
        self.images = {}
        for spec in FRAMES:
            if spec.image:
                w = FrameImage(spec)
                self.images[spec.key] = w
                il.addWidget(w, 1)
        root.addWidget(images, 3)

        self.table = QTableWidget(len(FRAMES), len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # per row: total or mean count, for the row, its image caption and the trend
        self.stat_combos = {}
        for r, spec in enumerate(FRAMES):
            combo = QComboBox()
            combo.addItems(STATS)
            combo.setToolTip("total: the counts summed over the stored frame; mean: per pixel")
            combo.currentTextChanged.connect(lambda _t, k=spec.key: self._on_stat_changed(k))
            self.stat_combos[spec.key] = combo
            self.table.setCellWidget(r, self.STAT_COL, combo)
        self.values_section = Section("Diagnostic values", self.table, expanded=False)
        root.addWidget(self.values_section, 0)

        trend = QWidget()
        tl = QVBoxLayout(trend)
        tl.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.trend_title = QLabel("Per-shot total of")
        row.addWidget(self.trend_title)
        self.trend_combo = QComboBox()
        for spec in FRAMES:
            self.trend_combo.addItem(f"{spec.label} ({spec.camera})", spec.key)
        self.trend_combo.currentIndexChanged.connect(lambda _i: self._refresh_trend())
        row.addWidget(self.trend_combo)
        note = QLabel("filled: at the reference's settings and frame size · hollow: not · "
                      "dashed: reference, dotted: ±1 σ")
        note.setStyleSheet(f"color: {theme.FG_MUTED};")
        row.addWidget(note, 1)
        tl.addLayout(row)
        self.trend = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.trend.setLabel("left", "mean count", units="DN")
        self.trend.showGrid(x=True, y=True, alpha=0.2)
        self.trend_same = pg.ScatterPlotItem(size=6, pen=None, brush=pg.mkBrush(theme.ACCENT))
        self.trend_other = pg.ScatterPlotItem(size=6, pen=pg.mkPen(theme.FG_MUTED), brush=None)
        self.trend.addItem(self.trend_same)
        self.trend.addItem(self.trend_other)
        self.ref_lines = [pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(
            theme.WARN, width=1.5, style=s)) for s in (Qt.PenStyle.DashLine, Qt.PenStyle.DotLine,
                                                       Qt.PenStyle.DotLine)]
        for ln in self.ref_lines:
            ln.setVisible(False)
            self.trend.addItem(ln)
        tl.addWidget(self.trend, 1)
        self.trend_section = Section("Trend", trend, expanded=True)
        root.addWidget(self.trend_section, 2)
        self.trend_section.toggled.connect(
            lambda on: root.setStretchFactor(self.trend_section, 2 if on else 0))

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {theme.FG_MUTED}; font-size: 11px;")
        root.addWidget(self.status)

    # -- network -----------------------------------------------------------

    def start(self):
        """Find liveOD's broadcast, subscribe, and fetch the latest frames."""
        self.fetcher = AuxFetcher()
        self.fetcher.fetched.connect(self.on_fetched)
        self.fetcher.status.connect(self._set_status)
        self.fetcher.start()
        self.fetcher.request(self._wanted(FRAME_KEYS))
        threading.Thread(target=self._discover_broadcast, daemon=True).start()
        self._load_newest_reference()

    def _discover_broadcast(self):
        while not self._closing:
            found = discover_endpoint("live_od_broadcast", timeout=3.0)
            if found is not None:
                self._endpoint_found.emit(str(found[0]), int(found[1]))
                return

    def _start_subscriber(self, ip, port):
        if self._closing:
            return
        from waxx.util.live_od.gui.remote_viewer_window import LiveODSubscriber  # noqa: PLC0415
        s = LiveODSubscriber(ip, port)
        s.aux_notice_signal.connect(self.on_aux_notice)
        s.run_started_signal.connect(lambda rid, _x: self.on_run_started(rid))
        s.run_done_signal.connect(self.on_run_done)
        s.run_state_signal.connect(self.on_run_state)
        s.shot_progress_signal.connect(self.on_shot_progress)
        s.connection_status_signal.connect(self.conn_label.setText)
        self.subscriber = s
        s.start()

    def shutdown(self):
        self._closing = True
        for t in (self.subscriber, self.fetcher):
            if t is not None:
                t.stop()
        for t in (self.subscriber, self.fetcher):
            if t is not None:
                t.wait(2000)
        self.subscriber = self.fetcher = None

    def closeEvent(self, ev):
        self.shutdown()
        super().closeEvent(ev)

    @staticmethod
    def _wanted(keys):
        out = []
        for k in keys:
            out += [k, k + "_meta"]
        return out

    # -- liveOD events -----------------------------------------------------

    def on_aux_notice(self, notice):
        rid = notice.get("run_id")
        if rid is not None and rid != self.run_id:
            self.on_run_started(int(rid))
        keys = {it.get("key") for it in notice.get("items", []) if it.get("index") is not None}
        keys = {k[:-5] if k.endswith("_meta") else k for k in keys if k}
        keys &= set(FRAME_KEYS)
        if keys and self.fetcher is not None:
            self.fetcher.request(self._wanted(sorted(keys)))

    def on_run_started(self, run_id):
        if run_id == self.run_id and not self.run_done:
            return
        self.run_id = int(run_id)
        self.run_done = False
        self.shot_text = ""
        self._update_run_label()
        self._refresh_table()

    def on_run_done(self):
        self.run_done = True
        self._update_run_label()
        self._refresh_table()

    def on_run_state(self, state, _detail=""):
        self.run_state = state
        self._update_run_label()

    def on_shot_progress(self, shot_idx, n_total, _xvars=None):
        self.shot_text = f"shot {shot_idx + 1}/{n_total}"
        self._update_run_label()

    def _update_run_label(self):
        parts = [f"Run {self.run_id}" if self.run_id is not None else "Run —"]
        if self.shot_text:
            parts.append(self.shot_text)
        if self.run_done:
            parts.append("done")
        elif self.run_state:
            parts.append(self.run_state)
        self.run_label.setText(" · ".join(parts))

    def on_fetched(self, items):
        """GET_AUX_DATA's items: each frame with its record, into the history."""
        changed = set()
        for key in FRAME_KEYS:
            img = items.get(key)
            if not img:
                continue
            meta = items.get(key + "_meta")
            if meta is not None and (meta.get("run_id") != img.get("run_id")
                                     or meta.get("index") != img.get("index")):
                continue        # not this frame's record: the next fetch brings both
            rid = img.get("run_id")
            if rid is None:
                continue
            st = frame_stats(img.get("array"), None if meta is None else meta.get("array"),
                             rid, img.get("index"), img.get("t", time.time()))
            if st is None:      # a cleared slot or a placeholder: not a frame
                continue
            tag = (st.run_id, st.index, st.seq)
            if self._shown.get(key) == tag:
                continue
            self._shown[key] = tag
            self.history.add(key, st)
            changed.add(key)
            if key in self.images:
                self.images[key].show_frame(img.get("array"), self._caption(key, st))
            if self.run_id is None or st.run_id > self.run_id:
                self.on_run_started(st.run_id)
        if changed:
            self._refresh_table()
            if self.trend_combo.currentData() in changed:
                self._refresh_trend()

    # -- numbers -----------------------------------------------------------

    def _key_ref(self, key):
        return None if self.reference is None else self.reference["keys"].get(key)

    def stat_for(self, key):
        """The row's choice: "total" (default) or "mean"."""
        combo = self.stat_combos.get(key)
        return combo.currentText() if combo is not None else STATS[0]

    def _on_stat_changed(self, key):
        st = self.history.latest(key)
        if key in self.images and st is not None:
            self.images[key].caption.setText(self._caption(key, st))
        self._refresh_table()
        if self.trend_combo.currentData() == key:
            self._refresh_trend()

    def _compare(self, value, exposure, gain, n_pixels, kr, stat):
        return compare(value, exposure, gain, kr, stat=stat, n_pixels=n_pixels)

    def _caption(self, key, st):
        stat = self.stat_for(key)
        text = (f"run {st.run_id} shot {fmt_index(st.index)} · {stat} "
                f"{fmt_count(stat_value(st, stat), stat)} DN · max {st.max:.0f} · "
                f"{fmt_settings(st.exposure, st.gain)}")
        kr = self._key_ref(key)
        if kr and kr.get("n"):
            c = self._compare(stat_value(st, stat), st.exposure, st.gain, st.n_pixels, kr, stat)
            if "reason" in c:
                text += f"<br>reference: {c['reason']}"
            else:
                d, _tip = fmt_compare(c)
                text += f"<br>reference {fmt_count(reference_stat(kr, stat)[0], stat)} DN → Δ {d}"
        if st.n_saturated:
            text += f"<br><span style='color:{theme.WARN}'>{st.n_saturated} px saturated: " \
                    f"{stat} is a lower bound</span>"
        return text

    def _status_for(self, key):
        """Why there is no frame from the current run (None when there is one)."""
        if self.configured is not None and key not in self.configured:
            return "not in diagnostic_cameras"
        if self.run_id is None:
            return "waiting for a run"
        if self.history.run_entries(key, self.run_id):
            return None
        others = any(self.history.run_entries(k, self.run_id) for k in FRAME_KEYS if k != key)
        if self.run_done:
            return "no frame this run (camera not used / no frame received)"
        return "no frame yet this run" if others else "waiting for frames"

    def _refresh_table(self):
        muted = QColor(theme.FG_MUTED)
        warn = QColor(theme.WARN)
        col = {c: i for i, c in enumerate(self.COLS)}
        n_this_run = n_saturated = n_settings = 0
        for r, spec in enumerate(FRAMES):
            key = spec.key
            stat = self.stat_for(key)
            latest = self.history.latest(key)
            summ = (run_summary(self.history, key, self.run_id, stat)
                    if self.run_id is not None else None)
            kr = self._key_ref(key)
            missing = self._status_for(key)
            cells = {c: "—" for c in self.COLS}
            cells.update({"Frame": spec.label, "Camera": spec.camera, "Notes": ""})
            tips = {"Frame": key}
            notes, note_warn = [], False
            stale = latest is not None and latest.run_id != self.run_id
            if not missing:
                n_this_run += 1
            if latest is not None:
                cells["Shot (DN)"] = (fmt_count(stat_value(latest, stat), stat)
                                      + (f"  (run {latest.run_id})" if stale else ""))
                tips["Shot (DN)"] = (f"run {latest.run_id}, shot {fmt_index(latest.index)}, "
                                     f"max {latest.max:.0f} DN, {latest.n_pixels} px")
                cells["Exposure / gain"] = fmt_settings(latest.exposure, latest.gain)
                if latest.n_saturated:
                    notes.append(f"{latest.n_saturated} px saturated (lower bound)")
                    note_warn = True
                    n_saturated += not stale
                elif latest.n_saturated is None:
                    tips["Notes"] = "saturation not checked: not an 8-bit frame"
            if summ is not None:
                cells["Run mean ± sem (DN)"] = (f"{fmt_count(summ['mean'], stat)} ± "
                                                f"{fmt_count(summ['sem'], stat)}  (n={summ['n']})")
                tips["Run mean ± sem (DN)"] = f"mean over this run's shots of each shot's {stat}"
                if summ["n_other_settings"]:
                    notes.append(f"{summ['n_other_settings']} shot(s) this run at other settings "
                                 f"or frame size, not in the run mean")
                if summ["n_shots_saturated"]:
                    notes.append(f"{summ['n_shots_saturated']} saturated shot(s) this run")
                    note_warn = True
            if kr and kr.get("n"):
                ms = reference_stat(kr, stat)
                if ms is None:
                    cells["Reference (DN)"] = "no total"
                    tips["Reference (DN)"] = "saved without its frame size: only its mean compares"
                else:
                    cells["Reference (DN)"] = (f"{fmt_count(ms[0], stat)} ± {fmt_count(ms[1], stat)}"
                                               f" σ  (n={kr['n']})")
                    tips["Reference (DN)"] = f"taken at {fmt_settings(kr['exposure'], kr['gain'])}"
                if latest is not None:
                    cells["Δ shot"], tips["Δ shot"] = fmt_compare(self._compare(
                        stat_value(latest, stat), latest.exposure, latest.gain, latest.n_pixels,
                        kr, stat))
                if summ is not None:
                    cells["Δ run"], tips["Δ run"] = fmt_compare(self._compare(
                        summ["mean"], summ["exposure"], summ["gain"], summ["n_pixels"], kr, stat))
                if latest is not None and not same_settings(latest.exposure, latest.gain,
                                                            kr["exposure"], kr["gain"]):
                    notes.append(f"settings differ from the reference "
                                 f"({fmt_settings(kr['exposure'], kr['gain'])})")
                    note_warn = True
                    n_settings += not stale
            if missing:
                notes.insert(0, missing)
            cells["Notes"] = "; ".join(notes)
            for name, text in cells.items():
                if name == "Quantity":
                    continue
                c = col[name]
                item = QTableWidgetItem(text)
                if tips.get(name):
                    item.setToolTip(tips[name])
                if name in ("Shot (DN)", "Run mean ± sem (DN)", "Reference (DN)", "Δ shot", "Δ run"):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if (stale and name == "Shot (DN)") or \
                        (missing and name in ("Shot (DN)", "Run mean ± sem (DN)")):
                    item.setForeground(muted)
                if name == "Notes" and note_warn:
                    item.setForeground(warn)
                self.table.setItem(r, c, item)
        self._fit_table_height()
        parts = [f"{n_this_run}/{len(FRAMES)} frames this run" if self.run_id is not None
                 else "no run yet"]
        if n_saturated:
            parts.append(f"{n_saturated} with saturated pixels")
        if n_settings:
            parts.append(f"{n_settings} at other settings than the reference")
        self.values_section.summary.setText(" · ".join(parts))

    def _fit_table_height(self):
        """The whole table, no scroll bar: it is short and folds away."""
        t = self.table
        h = t.horizontalHeader().height() + t.verticalHeader().length() + 2 * t.frameWidth()
        if t.horizontalScrollBar().isVisible():
            h += t.horizontalScrollBar().height()
        t.setFixedHeight(h)

    def _on_table_selection(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.trend_combo.setCurrentIndex(rows[0].row())

    def _refresh_trend(self):
        key = self.trend_combo.currentData()
        stat = self.stat_for(key)
        self.trend_title.setText(f"Per-shot {stat} of")
        self.trend.setLabel("left", f"{stat} count", units="DN")
        entries = self.history.entries(key)[-1000:]
        kr = self._key_ref(key)
        if kr and kr.get("n"):
            ref_e, ref_g, ref_n = kr["exposure"], kr["gain"], kr.get("n_pixels")
        elif entries:
            ref_e, ref_g, ref_n = entries[-1].exposure, entries[-1].gain, entries[-1].n_pixels
        else:
            ref_e = ref_g = ref_n = math.nan

        def matches(e):
            same_size = not _fin(ref_n) or int(ref_n) == e.n_pixels
            return same_settings(e.exposure, e.gain, ref_e, ref_g) and same_size
        same = [e for e in entries if matches(e)]
        other = [e for e in entries if not matches(e)]
        self.trend_same.setData([e.t for e in same], [stat_value(e, stat) for e in same])
        self.trend_other.setData([e.t for e in other], [stat_value(e, stat) for e in other])
        ms = reference_stat(kr, stat) if (kr and kr.get("n")) else None
        show = bool(ms and _fin(ms[0]))
        vals = [ms[0], ms[0] - ms[1], ms[0] + ms[1]] if show else []
        for i, ln in enumerate(self.ref_lines):
            ok = show and _fin(vals[i])
            ln.setVisible(ok)
            if ok:
                ln.setValue(vals[i])

    # -- references --------------------------------------------------------

    def _in_background(self, fn, on_done):
        def work():
            try:
                res, exc = fn(), None
            except Exception as e:      # noqa: BLE001 - reported in the GUI
                res, exc = None, e
            self._bg.done.emit(on_done, res, exc)
        threading.Thread(target=work, daemon=True).start()

    def _on_bg_done(self, cb, res, exc):
        if not self._closing:
            cb(res, exc)

    def _set_status(self, text):
        self.status.setText(f"{datetime.now():%H:%M:%S}  {text}")

    def apply_reference(self, ref, how="loaded"):
        self.reference = ref
        if ref is None:
            self.ref_label.setText("reference: none loaded")
        else:
            self.ref_label.setText(f"reference: {self._ref_when(ref)} · runs {ref.get('runs') or '?'}"
                                   f" · last {ref.get('window')} shots")
            self._set_status(f"reference {how}: {self._ref_when(ref)}")
        for key, st in ((k, self.history.latest(k)) for k in self.images):
            if st is not None:
                self.images[key].caption.setText(self._caption(key, st))
        self._refresh_table()
        self._refresh_trend()

    @staticmethod
    def _ref_when(ref):
        try:
            return datetime.fromisoformat(ref["datetime_iso"]).strftime("%Y-%m-%d %H:%M")
        except (KeyError, TypeError, ValueError):
            return datetime.fromtimestamp(ref["timestamp_s"]).strftime("%Y-%m-%d %H:%M")

    def _load_newest_reference(self):
        if not self.store.path:
            self._set_status("no reference file configured: references are not kept")
            return

        def done(refs, exc):
            if isinstance(exc, FileNotFoundError):
                return
            if exc is not None:
                self._set_status(f"could not read references: {exc}")
            elif refs:
                self.apply_reference(refs[0], "auto-loaded (newest)")
        self._in_background(self.store.load, done)

    def set_reference(self):
        window = int(self.window_spin.value())
        ref, notes = build_reference(self.history, window)
        if ref is None:
            QMessageBox.information(self, "Set reference", "No frames seen yet: nothing to "
                                    "take a reference from.")
            return
        lines = [f"{SPEC[k].label} ({SPEC[k].camera}): "
                 + (f"{fmt_dn(v['mean'])} ± {fmt_dn(v['std'])} DN, n={v['n']}, "
                    f"{fmt_settings(v['exposure'], v['gain'])}" if v["n"] else "no frames")
                 for k, v in ref["keys"].items()]
        text = (f"Reference from the last {window} shots of each frame (runs {ref['runs']}):\n\n"
                + "\n".join(lines))
        if notes:
            text += "\n\nNote:\n" + "\n".join(f"• {n}" for n in notes)
        text += "\n\nSave this reference" + (f" to\n{self.store.path}?" if self.store.path
                                             else " (no file configured: this session only)?")
        if QMessageBox.question(self, "Set reference", text) != QMessageBox.StandardButton.Yes:
            return
        if not self.store.path:
            self.apply_reference(ref, "set (not saved)")
            return

        def done(_res, exc):
            if exc is not None:
                QMessageBox.critical(self, "Set reference", f"Could not save the reference:\n{exc}")
                return
            self.apply_reference(ref, "set and saved")
        self._in_background(lambda: self.store.append(ref), done)

    def clear_reference(self):
        self.apply_reference(None)
        self._set_status("reference cleared (still saved; Load… brings it back)")

    def open_load_dialog(self):
        if not self.store.path:
            QMessageBox.information(self, "Load reference", "No reference file is configured.")
            return

        def done(refs, exc):
            if isinstance(exc, FileNotFoundError):
                QMessageBox.information(self, "Load reference",
                                        f"No references saved yet:\n{self.store.path}")
            elif exc is not None:
                QMessageBox.critical(self, "Load reference", str(exc))
            elif not refs:
                QMessageBox.information(self, "Load reference", "No valid references in the file.")
            else:
                ReferenceDialog(self, refs).exec()
        self._in_background(self.store.load, done)


class ReferenceDialog(QDialog):
    """The saved references, newest first: load one, or delete one from the file."""

    def __init__(self, viewer: DiagnosticViewer, refs):
        super().__init__(viewer)
        self.viewer = viewer
        self.refs = list(refs)
        self.setWindowTitle("Load reference")
        self.resize(760, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Pick a saved reference (values: mean count per pixel, DN). "
                             "✕ deletes it from the file."))
        self.cols = ["Date", "Runs", "Shots"] + [f"{SPEC[k].label} ({SPEC[k].camera.replace(' basler', '')})"
                                                 for k in FRAME_KEYS] + [""]
        self.table = QTableWidget(0, len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda _i: self._load())
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        load = QPushButton("Load")
        cancel = QPushButton("Cancel")
        load.clicked.connect(self._load)
        cancel.clicked.connect(self.reject)
        row.addWidget(load)
        row.addWidget(cancel)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        self.table.setRowCount(0)
        for r, ref in enumerate(self.refs):
            self.table.insertRow(r)
            vals = [DiagnosticViewer._ref_when(ref), str(ref.get("runs", "")), str(ref.get("window", ""))]
            for k in FRAME_KEYS:
                kr = ref["keys"].get(k, {})
                vals.append(fmt_dn(kr.get("mean")) if kr.get("n") else "—")
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if ref.get("note"):
                    it.setToolTip(ref["note"])
                self.table.setItem(r, c, it)
            btn = QPushButton("✕")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda _c=False, ts=ref["timestamp_s"]: self._delete(ts))
            self.table.setCellWidget(r, len(self.cols) - 1, btn)
        if self.refs:
            self.table.selectRow(0)

    def _load(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.refs):
            self.viewer.apply_reference(self.refs[r])
            self.accept()

    def _delete(self, ts):
        ref = next((x for x in self.refs if x["timestamp_s"] == ts), None)
        if ref is None:
            return
        if QMessageBox.question(self, "Delete reference",
                                f"Delete the reference of {DiagnosticViewer._ref_when(ref)} "
                                f"from the file?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.refs = self.viewer.store.delete(ts)
        except Exception as exc:        # noqa: BLE001
            QMessageBox.critical(self, "Delete reference", str(exc))
            return
        self._fill()


def main():
    try:
        import ctypes  # noqa: PLC0415
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("kexp.diagnostic_viewer")
    except Exception:
        pass
    app = QApplication(sys.argv)
    try:
        theme.apply_dark_theme(app)
        app.setStyleSheet(theme.app_stylesheet())
    except Exception:
        pass
    w = DiagnosticViewer()
    w.resize(1400, 950)
    w.show()
    sys.exit(app.exec())


__all__ = ["DiagnosticViewer", "ReferenceDialog", "main"]
