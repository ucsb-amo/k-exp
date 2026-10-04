"""The SLM spot finder's triggered scans, offline: frames on ARTIQ TTL edges.

The camera is the fake Andor of test_spot_finder_scan (a PatternBackend on a
real beacon CameraServerCore, 127.0.0.1, never beaconing) whose run frames
here expose at the trigger edge, as the real camera does; the ARTIQ pulser is
a fake whose pulse() is the edge reaching that camera.  No hardware, no lab
network, no core device, no monitor server.

What is checked is the pairing the triggered mode exists for: every frame
filed under the position whose pulse exposed it, a frame the camera lost a
missing frame at its own position (and nothing shifted after it), a stray
edge counted and never filed, and the hold ended -- camera unlocked, live
profile back, core released -- however the scan ends: finished, liveOD taking
the Andor, another program taking the core.
"""
import os
import threading
import time

import numpy as np
import pytest

import test_spot_finder_scan as base
from test_spot_finder_scan import (  # noqa: F401  (fixtures)
    app, slm_host, served_env, host,
    ANDOR_ID, MODE_CODE, FakeCamera, FakeSLM, SLMPattern, build_window, close_window,
    exposed_at, liveod_claimer, make_served, mode_of, needs_served, pattern_backend,
    process_until, run_scan, scan_grid, scan_group, served_window, wait_until)

from waxx.control.artiq.ttl_pulser import CoreTaken, PulserNotHeld

pytestmark = needs_served


class TriggeredPatternBackend(base.PatternBackend):
    """PatternBackend whose run frames expose AT the trigger edge (the real
    camera's external trigger starts the exposure), and whose lose_next()
    works in run mode (a frame the camera reports lost, never published)."""

    def _produce(self):
        if self._mode == "run":
            self._exp_start = self.pattern.get()
        if self._lose > 0:
            from beacon.camera.backend import RawFrame
            self._lose -= 1
            idx = self._produced
            self._produced += 1
            self._pending.append(RawFrame(None, hw_idx=idx, hw_ts=idx, t_host=time.time()))
            if self._n_max is not None and self._produced >= self._n_max:
                self._mode = None
            return
        super()._produce()


def triggered_backend(pattern):
    b = TriggeredPatternBackend(pattern)
    b.ranges["gain"] = (0, 300)
    return b


class FakePulser:
    """The ARTIQ side as the source sees it: acquire / pulse / release.  A
    pulse is the edge reaching the (fake) camera."""

    def __init__(self, backend, fail_pulse_at=None, run_check=None):
        self.backend = backend
        self.fail_pulse_at = fail_pulse_at
        self.run_check = run_check
        self.held = False
        self.acquires = self.releases = self.n_pulses = 0
        self.run_checks = []
        self.t_pulse = 200e-9

    def acquire(self):
        self.held = True
        self.acquires += 1
        return ["fake pulser: core taken (announced, precompiled)"]

    def pulse(self):
        if not self.held:
            raise PulserNotHeld("fake pulser: pulse() before acquire()")
        self.n_pulses += 1
        if self.fail_pulse_at is not None and self.n_pulses >= self.fail_pulse_at:
            raise CoreTaken("fake pulser: the connection to the core device was reset")
        t = time.monotonic()
        self.backend.trigger(1)
        return t

    def release(self):
        self.held = False
        self.releases += 1
        if self.run_check is not None:
            self.run_checks.append(self.run_check())
        return ["fake pulser: core released; the monitor restarts"]

    def describe(self):
        return "fake pulser: ttl7, 200 ns"

    def close(self):
        self.release()


def open_triggered(served_env, pattern=None, **kw):
    pattern = pattern or SLMPattern()
    backend = triggered_backend(pattern)
    src = make_served(lambda: backend, sources=served_env["sources"], **kw)
    src.open()
    pulser = FakePulser(backend)
    src.set_trigger(pulser)
    return src, backend, pulser, pattern


def scan(src, pattern, points, snap=None, set_center=None, settle_s=0.005, slm=None):
    slm = slm or FakeSLM(pattern, delay_s=0.0, confirms=True)
    timeout = scan_group.frame_timeout_s(src)
    src.plan_scan(len(points))
    src.begin_scan()
    try:
        shots, outcome = run_scan(points, set_center or slm.set_center_and_wait,
                                  snap or (lambda: src.snap(timeout)), settle_s,
                                  should_stop=lambda: False, on_shot=lambda s: None)
    finally:
        src.end_scan()
    return shots, outcome, slm


def test_triggered_scan_pairs_each_frame_to_its_own_pulse(served_env):
    from served_source import TRIGGER_FRAME_MARGIN
    src, backend, pulser, pattern = open_triggered(served_env)
    assert src.supports_trigger and src.triggered and src.trigger is pulser
    assert src.trigger_refusal == ""
    _, _, points = scan_grid(100, 200, R=1, step=1, canvas_res=(1920, 1200))

    src.plan_scan(len(points))
    src.begin_scan()
    # armed: the core taken first, then the worker locked and armed with a RUN
    # profile -- external trigger, the panel's exposure and gain, shutter open
    assert pulser.acquires == 1 and pulser.held
    assert src.worker.locked_by is not None
    profile, purpose = backend.applied[-1]
    assert purpose == "run"
    assert profile["trigger_mode"] == "ext" and profile["shutter"] == "open"
    assert profile["exposure_time"] == pytest.approx(src._exposure_s)
    assert profile["gain"] == 0
    assert {k: profile[k] for k in base.READOUT} == base.READOUT
    assert backend.acquisitions[-1] == ("run", len(points) + TRIGGER_FRAME_MARGIN)
    with pytest.raises(RuntimeError, match="during a triggered scan"):
        src.set_trigger(None)

    slm = FakeSLM(pattern, delay_s=0.0, confirms=True)
    timeout = scan_group.frame_timeout_s(src)
    shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: src.snap(timeout), 0.005,
                              should_stop=lambda: False, on_shot=lambda s: None)
    assert outcome.startswith("finished") and len(shots) == len(points)
    for s in shots:
        assert mode_of(s.frame) == MODE_CODE["run"], s.point
        assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2, s.point
    assert pulser.n_pulses == len(points)
    assert src.worker.locked_by is not None             # held until end_scan

    src.end_scan()
    assert pulser.releases == 1 and not pulser.held
    assert src.worker.locked_by is None
    assert wait_until(lambda: src.worker.state == "idle")
    live, purpose = backend.applied[-1]
    assert purpose == "live" and live["trigger_mode"] == "int"
    r = src.last_trigger_report
    assert r["paired"] == r["pulses"] == r["delivered"] == len(points)
    assert r["strays"] == r["gaps"] == r["lost"] == r["timeouts"] == r["foreign"] == 0
    assert r["preempted"] == "" and r["errors"] == []
    assert r["profile"]["trigger_mode"] == "ext"
    assert "9/9 pulses gave a frame" in base.served_source.trigger_summary(r) \
        if hasattr(base, "served_source") else True

    # the camera is back in the panel's hands: video and plain snaps work
    frames, stopped = [], threading.Event()
    src.start_video(frames.append, stopped.set)
    assert wait_until(lambda: len(frames) >= 2)
    assert all(mode_of(f) == MODE_CODE["live"] for f in frames)
    src.stop_video()
    src.set_trigger(None)
    assert not src.triggered
    src.begin_scan()
    f = src.snap(timeout)
    src.end_scan()
    assert mode_of(f) == MODE_CODE["snap"]


def test_a_lost_frame_is_a_missing_frame_at_its_position_and_nothing_shifts(served_env):
    src, backend, pulser, pattern = open_triggered(served_env)
    _, _, points = scan_grid(100, 200, R=1, step=1, canvas_res=(1920, 1200))
    n = {"snaps": 0}

    def snap():
        n["snaps"] += 1
        if n["snaps"] == 3:
            backend.lose_next(1)          # the camera loses the frame this pulse exposes
        return src.snap(0.3)

    shots, outcome, _ = scan(src, pattern, points, snap=snap)
    assert outcome.startswith("finished") and len(shots) == len(points)
    assert shots[2].frame is None and "no frame within" in shots[2].error
    for s in shots[:2] + shots[3:]:
        assert s.frame is not None and exposed_at(s) == ((s.point.cx, s.point.cy),) * 2, s.point
        assert mode_of(s.frame) == MODE_CODE["run"]
    r = src.last_trigger_report
    assert r["paired"] == len(points) - 1 and r["pulses"] == len(points)
    assert r["timeouts"] == 1 and r["lost"] == 1 and r["gaps"] == 0
    assert r["lost_idx"] == [2]           # the worker's own account of the lost frame


def test_a_stray_edge_is_counted_and_never_filed(served_env):
    src, backend, pulser, pattern = open_triggered(served_env)
    _, _, points = scan_grid(100, 200, R=1, step=1, canvas_res=(1920, 1200))
    slm = FakeSLM(pattern, delay_s=0.0, confirms=True)
    n = {"moves": 0}

    def set_center(cx, cy):
        r = slm.set_center_and_wait(cx, cy)
        n["moves"] += 1
        if n["moves"] == 4:
            backend.trigger(1)            # an edge nobody fired, before this position's pulse
            time.sleep(0.05)              # it is published before the pulse is asked for
        return r

    shots, outcome, _ = scan(src, pattern, points, set_center=set_center, slm=slm)
    assert outcome.startswith("finished") and len(shots) == len(points)
    for s in shots:
        assert s.frame is not None and exposed_at(s) == ((s.point.cx, s.point.cy),) * 2, s.point
    r = src.last_trigger_report
    assert r["strays"] == 1 and r["paired"] == len(points) and r["gaps"] == 0
    assert r["delivered"] == len(points) + 1


def test_liveod_taking_the_andor_mid_scan_frees_the_lock_and_stops_the_scan(served_env):
    src, backend, pulser, pattern = open_triggered(served_env, hold_s=1.0)
    keeper = liveod_claimer(src)
    served_env["keepers"].append(keeper)
    _, _, points = scan_grid(100, 200, R=5, step=1, canvas_res=(1920, 1200))
    slm = FakeSLM(pattern, delay_s=0.0, confirms=True)
    claimed = []
    timer = threading.Timer(0.5, lambda: claimed.append(keeper.claim(ANDOR_ID, timeout_s=20.0)))
    src.plan_scan(len(points))
    src.begin_scan()
    timer.start()
    try:
        timeout = scan_group.frame_timeout_s(src)
        shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: src.snap(timeout),
                                  0.03, should_stop=lambda: False, on_shot=lambda s: None)
    finally:
        timer.join()
        src.end_scan()
    assert 0 < len(shots) < len(points), outcome
    assert "camera taken over by another program" in outcome, outcome
    assert "liveOD (on testhost, pid 1) took the Andor over" in outcome, outcome
    for s in shots:
        assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2 and mode_of(s.frame) == MODE_CODE["run"]
    # the hold ended before the close: liveOD's claim was answered, the camera is shut here
    assert claimed and claimed[0][0].server.server_id == base.SERVED_ID
    assert not backend.opened and src.lent_to()["label"] == "liveOD"
    assert src.worker.locked_by is None
    assert pulser.releases == 1 and not pulser.held
    r = src.last_trigger_report
    assert r["preempted"] == "reserved" and "took the Andor over" in r["preempt_detail"]
    assert r["paired"] == len(shots)
    # nothing is armed or triggered while liveOD has it
    from frame_source import Preempted
    with pytest.raises(Preempted):
        src.begin_scan()
    assert pulser.acquires == 1
    keeper.release(ANDOR_ID)
    assert wait_until(lambda: src.lent_to() is None)


def test_the_core_taken_by_another_program_stops_the_scan_without_filing(served_env):
    src, backend, pulser, pattern = open_triggered(served_env)
    pulser.fail_pulse_at = 3
    _, _, points = scan_grid(100, 200, R=1, step=1, canvas_res=(1920, 1200))
    slm = base.CountingSLM(pattern, delay_s=0.0)
    shots, outcome, _ = scan(src, pattern, points, slm=slm)
    assert len(shots) == 2, outcome
    assert "ARTIQ core taken by another program" in outcome, outcome
    assert "connection to the core device was reset" in outcome
    assert len(slm.calls) == 3                       # the position in flight was written, no more
    r = src.last_trigger_report
    # two edges were fired; the third pulse never reached the core
    assert r["preempted"] == "core_taken" and r["paired"] == 2 and r["pulses"] == 2
    assert pulser.n_pulses == 3
    # the camera is ours still: unlocked, live profile back
    assert src.worker.locked_by is None and backend.applied[-1][1] == "live"
    assert pulser.releases == 1


def test_triggered_frame_takes_one_frame_and_disarms(served_env):
    src, backend, pulser, pattern = open_triggered(served_env)
    frame, report = src.triggered_frame(1.0)
    assert mode_of(frame) == MODE_CODE["run"] and tuple(frame[0]) == (0, 0, 0, 0)
    assert report["paired"] == report["pulses"] == 1
    assert pulser.acquires == pulser.releases == 1
    assert src.worker.locked_by is None and backend.applied[-1][1] == "live"
    assert report["pulser_notes"] == ["fake pulser: core released; the monitor restarts"]
    src.set_trigger(None)
    with pytest.raises(RuntimeError, match="no ARTIQ trigger"):
        src.triggered_frame(1.0)


@pytest.mark.skipif(not os.environ.get("db"), reason="needs the lab env var %db%")
def test_pulse_kernel_compiles_against_the_device_db():
    """The precompiled pulse kernel type-checks against the real Core and
    TTLOut of the lab's device db -- no core-device connection, as
    artiq_compile (~5 s).  Also pins what kexp's tables say the trigger is."""
    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from waxx.control.artiq.ttl_pulser import _PulseKernel
    from artiq_trigger import andor_trigger_spec, device_db_path, make_andor_trigger
    spec = andor_trigger_spec()
    assert spec["ttl_name"] == "ttl7" and spec["ttl_attr"] == "andor" and spec["channel"] == 7
    assert spec["t_pulse"] == pytest.approx(200e-9)
    pulser = make_andor_trigger()
    assert pulser.ttl_name == "ttl7" and pulser.ttl_state_name == "andor"
    assert pulser.label == "SLM spot finder (ARTIQ trigger)" and not pulser.held
    dmgr = DeviceManager(DeviceDB(device_db_path()))
    try:
        core, ttl = dmgr.get("core"), dmgr.get(spec["ttl_name"])
        assert type(ttl).__name__ == "TTLOut"
        k = _PulseKernel(core, ttl)
        core.compile(k.pulse, [spec["t_pulse"], 1e-3], {}, attribute_writeback=False,
                     print_as_rpc=False)
    finally:
        dmgr.close_devices()


def test_other_sources_say_they_take_no_triggered_frames(host):
    from frame_source import LocalAndorSource, STREAM_TRIGGER_REFUSAL
    local = LocalAndorSource(FakeCamera(SLMPattern()))
    assert local.supports_trigger is False and "SDK" in local.trigger_refusal
    stream = host.open_source()
    assert stream.supports_trigger is False and stream.trigger_refusal == STREAM_TRIGGER_REFUSAL
    assert "runs only" in stream.trigger_refusal


# ----------------------------------------------------------------------
# the window
# ----------------------------------------------------------------------

def test_window_triggered_scan_takes_frames_on_pulses(app, slm_host, monkeypatch, served_env):
    import SLM_andor_main_gui as main_gui
    pattern = SLMPattern()
    backend = triggered_backend(pattern)
    made = []

    def fake_pulser(run_check):
        made.append(FakePulser(backend, run_check=run_check))
        return made[-1]
    monkeypatch.setattr(main_gui, "make_trigger_pulser", fake_pulser)

    def served():
        src = make_served(lambda: backend, sources=served_env["sources"])
        made_sources.append(src)
        return src
    made_sources = []
    w = build_window(slm_host, monkeypatch, None, served=served, source_mode="direct")
    try:
        assert process_until(app, lambda: w._camera_connected() and w._gate_open)
        assert not w.trigger_status.isVisible() and not w.trigger_test_btn.isEnabled()
        assert w.source.trigger is None

        w.trigger_cb.setChecked(True)
        assert process_until(app, lambda: w._pulser is not None)
        pulser = made[0]
        assert w.source.trigger is pulser and w.source.triggered
        assert "triggered from ARTIQ" in w.trigger_status.text()
        assert w.trigger_test_btn.isEnabled()
        assert w._trigger_refusal() == ""

        # the fake camera looks at what the stubbed SLM server last uploaded
        pattern.get = lambda: tuple(slm_host.uploads[-1][1])
        shots_seen = []
        w.scan_R_sb.setValue(1)
        w.settle_sb.setValue(5)
        w.start_scan()
        assert w._scanning
        w.scan_worker.finished_sig.connect(lambda shots, outcome: shots_seen.append((shots, outcome)))
        assert not w.trigger_cb.isEnabled() and not w.trigger_test_btn.isEnabled()
        assert process_until(app, lambda: not w._scanning)
        shots, outcome = shots_seen[0]
        assert outcome.startswith("finished") and len(shots) == 9
        for s in shots:
            assert mode_of(s.frame) == MODE_CODE["run"]
            assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2
        assert pulser.acquires == pulser.releases == 1 and pulser.n_pulses == 9
        assert pulser.run_checks == [(True, "")]       # the window's liveOD check, at release
        text = w.scan_progress.text()
        assert "ARTIQ-triggered frames: 9/9 pulses gave a frame" in text, text
        assert "the monitor restarts" in text
        assert w.trigger_cb.isEnabled() and w.scan_btn.isEnabled()

        # the test button: one frame, shown, the camera handed back
        w.trigger_test_btn.click()
        assert w._trigger_testing
        assert process_until(app, lambda: not w._trigger_testing)
        assert w.trigger_status.text().startswith("Triggered frame OK: 1/1 pulses gave a frame")
        assert pulser.acquires == pulser.releases == 2
        assert w.source.worker.locked_by is None

        # unticked: the source snaps again
        w.trigger_cb.setChecked(False)
        assert w.source.trigger is None and not w.trigger_status.isVisible()
        assert not w.trigger_test_btn.isEnabled()
    finally:
        close_window(w)


def test_window_refuses_a_triggered_scan_the_source_cannot_take(app, slm_host, monkeypatch):
    import SLM_andor_main_gui as main_gui
    pattern = SLMPattern()
    camera = FakeCamera(pattern)                       # LocalAndorSource: the SDK directly
    monkeypatch.setattr(main_gui, "make_trigger_pulser",
                        lambda run_check: FakePulser(camera, run_check=run_check))
    w = build_window(slm_host, monkeypatch, camera, connect_camera_on_start=False)
    try:
        assert process_until(app, lambda: w._gate_open)
        w.trigger_cb.setChecked(True)
        assert process_until(app, lambda: w._pulser is not None)
        why = w._trigger_refusal()
        assert "SDK" in why and "Triggered frames unavailable" in w.trigger_status.text()
        assert not w.trigger_test_btn.isEnabled()
        w.scan_R_sb.setValue(1)
        w.start_scan()
        assert not w._scanning
        assert w.scan_progress.text().startswith("Not scanning:") and "SDK" in w.scan_progress.text()
        w.trigger_test_btn.click()
        assert not w._trigger_testing
        # unticked, the scan snaps as before
        w.trigger_cb.setChecked(False)
        pattern.get = lambda: tuple(slm_host.uploads[-1][1])
        w.start_scan()
        assert w._scanning
        assert process_until(app, lambda: not w._scanning)
        assert w.scan_progress.text().startswith("Scan finished")
    finally:
        close_window(w)


def test_window_reports_a_trigger_that_cannot_be_set_up(app, slm_host, monkeypatch):
    import SLM_andor_main_gui as main_gui

    def broken(run_check):
        raise RuntimeError("no device db here")
    monkeypatch.setattr(main_gui, "make_trigger_pulser", broken)
    w = build_window(slm_host, monkeypatch, FakeCamera(SLMPattern()), connect_camera_on_start=False)
    try:
        assert process_until(app, lambda: w._gate_open)
        w.trigger_cb.setChecked(True)
        assert process_until(app, lambda: not w._pulser_loading)
        assert w._pulser is None
        assert "ARTIQ trigger unavailable: RuntimeError: no device db here" in w._trigger_refusal()
        assert "unavailable" in w.trigger_status.text()
        w.start_scan()
        assert not w._scanning and "no device db here" in w.scan_progress.text()
    finally:
        close_window(w)
