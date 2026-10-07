"""Diagnostic viewer (kexp.util.guis.diagnostic_viewer): per-frame numbers,
the per-run tally, references (build, compare, CSV round trip in a temp
dir), and the window fed fake GET_AUX_DATA replies. Nothing goes on the
network (start=False); offscreen Qt."""
import math
import os

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from waxa.data.camera_frames import meta_row
from kexp.util.guis.diagnostic_viewer.frames import (
    FRAME_KEYS, FrameHistory, frame_stats, run_summary)
from kexp.util.guis.diagnostic_viewer.references import (
    ReferenceStore, build_reference, compare)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _frame(value, shape=(20, 30), dtype=np.uint8):
    return np.full(shape, value, dtype=dtype)


def _stats(value, run=1, idx=0, exposure=300e-6, gain=3.0, t=0.0, seq=None):
    return frame_stats(_frame(value), meta_row(seq=idx if seq is None else seq,
                                               exposure=exposure, gain=gain), run, [idx], t)


def test_frame_stats_mean_and_saturation():
    img = _frame(10)
    img[0, :5] = 255
    st = frame_stats(img, meta_row(seq=7, exposure=1e-3, gain=0.), 85000, [3], 1.0)
    assert st.mean == pytest.approx((10 * (600 - 5) + 255 * 5) / 600)
    assert st.n_saturated == 5 and st.max == 255
    assert (st.exposure, st.gain, st.index) == (1e-3, 0.0, (3,))


def test_cleared_slot_and_placeholder_are_not_frames():
    assert frame_stats(_frame(0), meta_row(), 1, [0], 0.) is None          # seq NaN: a clear
    assert frame_stats(np.zeros((1,), np.uint8), None, 1, [0], 0.) is None  # placeholder
    st = frame_stats(_frame(5, dtype=np.uint16), meta_row(seq=1), 1, [0], 0.)
    assert st.n_saturated is None                                           # not checked


def test_history_replaces_a_repeated_slot():
    h = FrameHistory()
    h.add("img_mot", _stats(10, idx=0))
    h.add("img_mot", _stats(20, idx=0))
    assert [e.mean for e in h.entries("img_mot")] == [20]


def test_run_summary_uses_the_latest_settings():
    h = FrameHistory()
    h.add("img_mot", _stats(100, idx=0, exposure=1e-3))
    for i, v in enumerate((10, 12, 14), start=1):
        h.add("img_mot", _stats(v, idx=i))
    s = run_summary(h, "img_mot", 1)
    assert s["n"] == 3 and s["mean"] == pytest.approx(12)
    assert s["sem"] == pytest.approx(2 / math.sqrt(3))
    assert s["n_other_settings"] == 1


def test_build_reference_window_and_settings_cut():
    h = FrameHistory()
    h.add("img_gm", _stats(50, run=1, idx=0, gain=30.))     # older settings: left out
    for i in range(5):
        h.add("img_gm", _stats(10 + i, run=2, idx=i, gain=20.))
    ref, notes = build_reference(h, window=4, now=1000.)
    g = ref["keys"]["img_gm"]
    assert g["n"] == 4 and g["mean"] == pytest.approx(12.5) and g["gain"] == 20.
    assert ref["runs"] == "2"
    assert ref["keys"]["img_mot"]["n"] == 0
    ref, notes = build_reference(h, window=10, now=1000.)
    assert ref["keys"]["img_gm"]["n"] == 5 and ref["keys"]["img_gm"]["n_excluded"] == 1
    assert any("other settings" in n for n in notes)
    assert build_reference(FrameHistory(), 5)[0] is None


def test_totals_compare_only_at_the_same_frame_size():
    kr = {"mean": 10., "std": 2., "n": 5, "exposure": 300e-6, "gain": 3., "n_pixels": 600}
    c = compare(7200., 300e-6, 3., kr, stat="total", n_pixels=600)
    assert c["delta_frac"] == pytest.approx(0.2) and c["z"] == pytest.approx(1.0)
    assert "reason" in compare(7200., 300e-6, 3., kr, stat="total", n_pixels=100)
    old = dict(kr, n_pixels=math.nan)       # a reference saved before frame sizes
    assert "reason" in compare(7200., 300e-6, 3., old, stat="total", n_pixels=600)
    assert "reason" not in compare(12., 300e-6, 3., old, stat="mean", n_pixels=600)


def test_compare_refuses_other_settings():
    kr = {"mean": 10., "std": 2., "n": 5, "exposure": 300e-6, "gain": 3.}
    c = compare(12., 300e-6, 3., kr)
    assert c["delta_frac"] == pytest.approx(0.2) and c["z"] == pytest.approx(1.0)
    assert "reason" in compare(12., 1e-3, 3., kr)
    assert "reason" not in compare(12., 300e-6, 2.999994321, kr)    # the camera's read-back
    assert "reason" in compare(12., 300e-6, 3.1, kr)
    assert "reason" in compare(12., math.nan, math.nan, kr)
    assert "reason" in compare(12., 300e-6, 3., None)


def test_reference_csv_round_trip(tmp_path):
    h = FrameHistory()
    for i in range(3):
        h.add("img_mot", _stats(10 + i, idx=i))
    store = ReferenceStore(str(tmp_path / "refs.csv"))
    with pytest.raises(FileNotFoundError):
        store.load()
    r1, _ = build_reference(h, 3, note="first", now=100.)
    r2, _ = build_reference(h, 2, now=200.)
    store.append(r1)
    store.append(r2)
    refs = store.load()
    assert [r["timestamp_s"] for r in refs] == [200., 100.]
    assert refs[1]["note"] == "first"
    m = refs[1]["keys"]["img_mot"]
    assert m["n"] == 3 and m["mean"] == pytest.approx(11) and m["exposure"] == pytest.approx(300e-6)
    assert m["n_pixels"] == 600
    assert refs[0]["keys"]["img_gm"]["n"] == 0 and math.isnan(refs[0]["keys"]["img_gm"]["mean"])
    assert [r["timestamp_s"] for r in store.delete(200.)] == [100.]
    assert len(store.load()) == 1
    assert [p.name for p in tmp_path.iterdir()] == ["refs.csv"]      # no temp file left


def _items(run, idx, frames):
    """A GET_AUX_DATA reply: ``frames`` = {key: (img, meta_row)}."""
    out = {}
    for key, (img, meta) in frames.items():
        out[key] = {"run_id": run, "key": key, "index": [idx], "array": img, "t": 1.0 + idx}
        out[key + "_meta"] = {"run_id": run, "key": key + "_meta", "index": [idx],
                              "array": meta, "t": 1.0 + idx}
    return out


def test_window_fed_fake_replies(qapp):
    from kexp.util.guis.diagnostic_viewer.window import DiagnosticViewer
    w = DiagnosticViewer(reference_csv_path=None, start=False)
    try:
        col = {c: i for i, c in enumerate(w.COLS)}
        row = {k: i for i, k in enumerate(FRAME_KEYS)}
        w.on_run_started(85000)
        for i, v in enumerate((10, 12, 14)):
            w.on_fetched(_items(85000, i, {
                "img_mot": (_frame(v), meta_row(seq=i, exposure=300e-6, gain=3.)),
                "img_mot_beams_xy": (_frame(255), meta_row(seq=i, exposure=19e-6, gain=0.)),
            }))
        # a cleared slot after the frames does not count
        w.on_fetched(_items(85000, 3, {"img_mot": (_frame(0), meta_row())}))
        t = w.table
        # folded by default, the trend open; the header still says how things are
        assert not w.values_section.expanded() and w.trend_section.expanded()
        assert w.values_section.summary.text().startswith("2/7 frames this run")
        assert "1 with saturated pixels" in w.values_section.summary.text()
        # every row starts on the total: 600 px x 14 DN
        assert all(c.currentText() == "total" for c in w.stat_combos.values())
        assert t.item(row["img_mot"], col["Shot (DN)"]).text() == "8.4 k"
        assert "(n=3)" in t.item(row["img_mot"], col["Run mean ± sem (DN)"]).text()
        assert t.item(row["img_mot"], col["Run mean ± sem (DN)"]).text().startswith("7.2 k ± 692.8")
        assert "saturated" in t.item(row["img_mot_beams_xy"], col["Notes"]).text()
        assert "no frame yet" in t.item(row["img_gm"], col["Notes"]).text()
        assert "total 8.4 k DN" in w.images["img_mot"].caption.text()

        ref, _ = build_reference(w.history, 3)
        w.apply_reference(ref)
        assert t.item(row["img_mot"], col["Reference (DN)"]).text().startswith("7.2 k ± 1.2 k σ")
        assert t.item(row["img_mot"], col["Δ shot"]).text().startswith("+16.7 %  (+1.0 σ)")
        # the row's dropdown: the mean, in the row, the caption and the trend
        w.stat_combos["img_mot"].setCurrentText("mean")
        assert t.item(row["img_mot"], col["Shot (DN)"]).text() == "14.0"
        assert t.item(row["img_mot"], col["Δ shot"]).text().startswith("+16.7 %")
        assert "mean 14.0 DN" in w.images["img_mot"].caption.text()
        w.trend_combo.setCurrentIndex(row["img_mot"])
        assert w.trend_title.text() == "Per-shot mean of"
        assert list(w.trend_same.getData()[1]) == [10., 12., 14.]
        assert w.ref_lines[0].value() == pytest.approx(12.)
        w.stat_combos["img_mot"].setCurrentText("total")
        assert w.ref_lines[0].value() == pytest.approx(7200.)
        # same settings, other frame size (a new ROI): not compared, total or mean
        w.on_fetched(_items(85000, 5, {"img_mot": (_frame(14, shape=(10, 10)),
                                                   meta_row(seq=5, exposure=300e-6, gain=3.))}))
        assert t.item(row["img_mot"], col["Δ shot"]).text() == "—"
        assert t.item(row["img_mot"], col["Δ shot"]).toolTip() ==             "frame size differs from the reference"
        # same frame at other settings: no delta, says why
        w.on_fetched(_items(85000, 6, {"img_mot": (_frame(30), meta_row(seq=6, exposure=1e-3,
                                                                         gain=3.))}))
        assert t.item(row["img_mot"], col["Δ shot"]).text() == "—"
        assert "settings differ" in t.item(row["img_mot"], col["Notes"]).text()

        w.on_run_done()
        assert "no frame this run" in t.item(row["img_gm"], col["Notes"]).text()
        # a notice for a new run switches the run; frames of the old one go grey
        w.on_aux_notice({"run_id": 85001, "items": [{"key": "img_mot", "index": [0]}]})
        assert w.run_id == 85001 and "(run 85000)" in t.item(row["img_mot"], col["Shot (DN)"]).text()
    finally:
        w.shutdown()
        w.deleteLater()
