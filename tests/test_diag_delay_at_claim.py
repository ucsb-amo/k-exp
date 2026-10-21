"""The diagnostic cameras' exposure delay in a real kexp experiment, cold and
warm: compiled in as a provisional value, decided at the claim with this
run's settings, taken by the kernel at its start (init_kernel / scan ->
waxx Scanner.load_exposure_delays). Run 87656 (2026-10-21) fired the 2D-MOT
and MOT baslers' frames 2.46 ms early: the kernel kept the camera server's
last report (23593 us, the previous run's settings), the camera said 21131 us
at the claim.

Same isolation as test_claim_split_compiles (whose builder this uses): every
network client stubbed, no socket leaves the machine, the cameras are
in-memory streams, the kernel is compiled offline and never run; its loader
is run on the host through its Python body.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_claim_split_compiles import (  # noqa: F401 (fixture)
    _FakeStream, _build, _cleanup, _compile, _kernel_view, no_outbound_sockets)

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

AT_CLAIM = 21131e-6
BEFORE = 23593e-6

AUTO_TOF = Path(__file__).resolve().parents[1] / "kexp" / "experiments" / "tools" / "auto_tof.py"


class _Entry:
    exposure_start_delay_s = BEFORE
    server_id = "camera_server:previous_run"


class _LeftoverDirectory:
    """The camera servers' directory as the previous run left it: every
    camera reports BEFORE (no network)."""
    def find(self, query, *, refresh=False):
        return _Entry()

    def close(self):
        pass


class _ClaimStream(_FakeStream):
    """A camera that reports AT_CLAIM once trigger mode is on (this run's
    settings), BEFORE otherwise."""
    def status(self, refresh=True):
        st = super().status(refresh)
        st.raw["exposure_start_delay_s"] = (AT_CLAIM if self._settings.get("trigger_mode") == "On"
                                            else BEFORE)
        return st


def _setup(monkeypatch):
    from waxx.control.cameras import camera_stream_client as csc
    monkeypatch.setattr(csc, "shared_camera_directory", _LeftoverDirectory)


def _use_claim_streams(monkeypatch):
    from waxx.control.cameras import camera_stream_client as csc

    def _resolve(self, directory):
        return _ClaimStream(self.serial)

    monkeypatch.setattr(csc.CameraStreamClient, "_resolve_and_connect", _resolve)


def _live_streams(exp):
    return [s for s in exp.diag.streams().values() if hasattr(s, "exposure_delay_cell")]


def _load(exp):
    from waxx.base.scanner import Scanner
    Scanner.load_exposure_delays.artiq_embedded.function(exp)


def _check_after_load(exp):
    streams = _live_streams(exp)
    assert streams
    for s in streams:
        assert s.exposure_delay_cell.value == AT_CLAIM == s.exposure_delay_at_connect
        assert s.exposure_delay_to_kernel == "loaded_at_kernel_start"
    rec = json.loads(exp._extra_file_texts["diagnostic_images"])["images"]
    for k, img in exp.diag.images().items():
        if img.live:
            assert img.exposure_delay_cell.value == AT_CLAIM
            assert rec[k]["exposure_delay"] == AT_CLAIM, k
            assert rec[k]["exposure_delay_source"] == "camera_at_claim"
            assert rec[k]["exposure_delay_before_claim"] == BEFORE
            assert rec[k]["exposure_delay_to_kernel"] == "loaded_at_kernel_start"
        else:
            assert rec[k]["exposure_delay"] is None


def test_warm_the_kernel_takes_the_claims_delay_not_the_compiled_one(monkeypatch, tmp_path,
                                                                     no_outbound_sockets):
    _setup(monkeypatch)
    b = _build(monkeypatch, tmp_path, warm=True)
    try:
        exp = b.exp
        streams = _live_streams(exp)
        assert streams and all(s.exposure_delay_cell.value == BEFORE for s in streams)
        embedding_map = _compile(b)[0]
        before = _kernel_view(embedding_map)
        cells = {k: v for k, v in before.items() if k[0].startswith("ExposureDelayCell")}
        assert len(cells) == len(streams) + 1                 # + the spare cell

        _use_claim_streams(monkeypatch)
        b.queue_gate.ensure_go()
        b.queue_gate.run_claim()
        after = _kernel_view(embedding_map)
        assert sorted(k for k in before if after.get(k) != before[k]) == []   # claim audit
        rec = json.loads(exp._extra_file_texts["diagnostic_images"])["images"]
        assert rec["img_2dmot"]["exposure_delay"] == BEFORE                  # not loaded yet
        assert rec["img_2dmot"]["exposure_delay_to_kernel"] == "compiled_in"
        assert rec["img_2dmot"]["exposure_delay_at_claim"] == AT_CLAIM

        _load(exp)                                            # the kernel's start
        _check_after_load(exp)
        _compile(b)                                           # a later kernel compiles too
    finally:
        _cleanup(b)


def test_cold_a_camera_reporting_no_delay_at_the_claim_gives_the_configured_one(
        monkeypatch, tmp_path, no_outbound_sockets, capsys):
    """The builder's own fake cameras report no delay: the claim (in
    finish_prepare) falls back to the configured value, loudly, and the
    kernel takes that -- not the provisional (directory) one."""
    _setup(monkeypatch)
    b = _build(monkeypatch, tmp_path, warm=False)
    try:
        exp = b.exp
        assert "not read from the camera at the claim" in capsys.readouterr().out
        _compile(b)
        _load(exp)
        for s in _live_streams(exp):
            assert s.exposure_delay_cell.value == s.exposure_delay_configured
            assert s.exposure_delay_cell.value != BEFORE
            assert s.exposure_delay_source == "configured"
            assert s.exposure_delay_to_kernel == "loaded_at_kernel_start"
    finally:
        _cleanup(b)


def test_cold_with_a_reporting_camera(monkeypatch, tmp_path, no_outbound_sockets):
    """As above, with the cameras reporting at the claim: the build's own
    connect stub is replaced before prepare() runs."""
    from waxx.control.cameras import camera_stream_client as csc
    _setup(monkeypatch)
    real_setattr = monkeypatch.setattr

    def setattr_keep_claim_stream(target, name, value, *a, **k):
        if target is csc.CameraStreamClient and name == "_resolve_and_connect":
            value = lambda self, directory: _ClaimStream(self.serial)    # noqa: E731
        return real_setattr(target, name, value, *a, **k)

    monkeypatch.setattr = setattr_keep_claim_stream
    try:
        b = _build(monkeypatch, tmp_path, warm=False)
    finally:
        monkeypatch.setattr = real_setattr
    try:
        _compile(b)
        _load(b.exp)
        _check_after_load(b.exp)
    finally:
        _cleanup(b)


def test_auto_tof_compiles_with_the_loader(monkeypatch, tmp_path, no_outbound_sockets):
    """A real diag-using experiment (the TOF loop's), compiled offline."""
    _setup(monkeypatch)
    # the builder writes the source in the locale encoding: its comments' non-ASCII out
    source = AUTO_TOF.read_text(encoding="utf-8").encode("ascii", "replace").decode("ascii")
    b = _build(monkeypatch, tmp_path, warm=False, source=source)
    try:
        embedding_map = _compile(b)[0]
        view = _kernel_view(embedding_map)
        cells = [k for k in view if k[0].startswith("ExposureDelayCell")]
        assert len(cells) == len(_live_streams(b.exp)) + 1
        assert any(k[1] == "_exposure_delays_loaded" for k in view)
    finally:
        _cleanup(b)
