"""A minimal FeedbackExpt-derived experiment compiles, with and without the MOT
pre-load, and declares no interleaved readout calibration (removed 2026-11-04).
Compile only, against the real device db (feedback_compile_harness). Skipped
without %db% / %code%. ~10 s per compile."""
import json
import os

import pytest

from feedback_compile_harness import _build, _compile

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")


@pytest.mark.parametrize("mot_preload", [False, True])
def test_the_feedback_run_compiles(monkeypatch, tmp_path, mot_preload):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, mot_preload=mot_preload)
    try:
        assert exp.mot_preload is mot_preload
        assert not any(k.startswith("cal_") for k in exp.data.keys)
        assert not hasattr(exp, "_subscan") and not hasattr(exp, "_subscan_enabled")
        assert not any(k.startswith("cal_") for k in vars(exp.p))
        assert "sub_scan" not in json.loads(exp._extra_file_texts["mot_preload"])
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()
