"""The SLM spot finder, offline: a fake camera, a fake stage, and the real SLM
run_server connection handling on localhost with the Meadowlark calls stubbed.
No hardware, no lab network.

What is checked is what the scan exists to get right: every frame is filed
under the SLM position that was up for the whole of its exposure. The fakes
model the timing that matters -- an acquisition's first exposure starts after
start_acquisition(), the SLM changes pattern some time after a command -- and
nothing else, so these tests say the sequencing is right, not that the Andor
or the Meadowlark behave like the fakes.

The StreamSource tests (the Andor taken through liveOD's camera host) run a
real beacon CameraServerCore, policy "persistent" as liveOD's host is, on
127.0.0.1 with a FakeBackend-derived camera whose frames encode the SLM
position -- found through a directory whose discovery is a dict, never UDP.
The core never beacons (QuietCore overrides it, and NetServer's beacon is
patched out too): this runs on kong, where a test server that advertised
itself as camera_server:*:liveod would be found by the lab.

SPOT_FINDER_DIR, if set, is the spot finder package to test instead of the one
in k-exp (a copy being worked on outside the guarded tree). Tests of the run
gate, the FrameSource seam and StreamSource skip on a package that predates them.
"""
import json
import os
import random
import socket
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPOT_FINDER = Path(os.environ.get("SPOT_FINDER_DIR")
                   or ROOT / "k-exp" / "kexp" / "calibrations" / "SLM_spot_finder")
SLM_WIRE_DIR = ROOT / "wax" / "waxx-src" / "waxx" / "control" / "slm" / "server"
sys.path.insert(0, str(SPOT_FINDER))
sys.path.insert(0, str(SLM_WIRE_DIR))

# The run gate and the FrameSource seam (2026-09-26).
HAS_SEAM = all((SPOT_FINDER / f).is_file() for f in ("run_gate.py", "frame_source.py"))
needs_seam = pytest.mark.skipif(
    not HAS_SEAM, reason=f"{SPOT_FINDER} predates the run gate and FrameSource")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from andor_group import snap_frame                                     # noqa: E402
import scan_group                                                      # noqa: E402
from scan_group import run_scan, scan_grid, shots_to_grid             # noqa: E402
from slm_group import SLMController, SLMSendResult                     # noqa: E402
import slm_group                                                       # noqa: E402
from slm_protocol import split_commands, command_seq                   # noqa: E402


# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------

class SLMPattern:
    """The pattern physically on the SLM."""

    def __init__(self, center=(0, 0)):
        self._lock = threading.Lock()
        self._center = tuple(center)

    def put(self, center):
        with self._lock:
            self._center = tuple(center)

    def get(self):
        with self._lock:
            return self._center


class FakeSLM:
    """set_center_and_wait() like SLMController, against SLMPattern.

    The pattern changes ``delay_s`` after the call. ``confirms=True`` blocks
    until it has (the updated server); ``False`` returns at once with
    applied=None (the old server, which never says).
    """

    def __init__(self, pattern, delay_s=0.03, confirms=True, fail_at=None):
        self.pattern = pattern
        self.delay_s = delay_s
        self.confirms = confirms
        self.fail_at = fail_at

    def set_center_and_wait(self, cx, cy):
        if self.fail_at == (cx, cy):
            return SLMSendResult(ok=False, center=(cx, cy), error="connection refused")
        t_sent = time.monotonic()
        delay = self.delay_s() if callable(self.delay_s) else self.delay_s
        timer = threading.Timer(delay, self.pattern.put, args=((cx, cy),))
        timer.start()
        if not self.confirms:
            return SLMSendResult(ok=True, center=(cx, cy), t_sent=t_sent)
        timer.join()
        return SLMSendResult(ok=True, applied=True, center=(cx, cy), t_sent=t_sent,
                             t_applied=time.monotonic())


class FakeCamera:
    """Free-running internal-trigger acquisition: exposure, readout, repeat.

    Each frame is [[x_start, y_start, x_end, y_end]], the SLM pattern at the
    start and at the end of its exposure. The first exposure of an
    acquisition begins when start_acquisition() is called.
    """

    def __init__(self, pattern, exposure_s=0.02, readout_s=0.01, dead=False):
        self.pattern = pattern
        self.exposure_s = exposure_s
        self.readout_s = readout_s
        self.dead = dead            # acquires, but never delivers a frame
        self._cv = threading.Condition()
        self._frames = []
        self._n_read = 0
        self._running = False
        self._thread = None
        self.closed = False

    def get_frame_timings(self):
        return (self.exposure_s, self.exposure_s + self.readout_s)

    def start_acquisition(self):
        self.stop_acquisition()
        with self._cv:
            self._frames, self._n_read, self._running = [], 0, True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            start = self.pattern.get()
            time.sleep(self.exposure_s)
            end = self.pattern.get()
            time.sleep(self.readout_s)
            with self._cv:
                if not self._running:
                    return
                if not self.dead:
                    self._frames.append(np.array([[*start, *end]], dtype=np.uint16))
                    self._cv.notify_all()

    def stop_acquisition(self):
        with self._cv:
            self._running = False
            self._cv.notify_all()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def clear_acquisition(self):
        self.stop_acquisition()

    def wait_for_frame(self, timeout=None):
        with self._cv:
            if not self._running:
                return False
            if not self._cv.wait_for(lambda: len(self._frames) > self._n_read, timeout=timeout):
                raise TimeoutError("fake camera: no frame")
            return True

    def read_multiple_images(self, return_info=False):
        with self._cv:
            new = self._frames[self._n_read:]
            self._n_read = len(self._frames)
            return new

    def Close(self):
        self.stop_acquisition()
        self.closed = True


def exposed_at(shot):
    x0, y0, x1, y1 = (int(v) for v in shot.frame[0])
    return (x0, y0), (x1, y1)


def run(points, slm, camera, settle_s):
    timeout = scan_group.frame_timeout_s(camera)
    return run_scan(points, set_center=slm.set_center_and_wait,
                    snap=lambda: snap_frame(camera, timeout), settle_s=settle_s,
                    should_stop=lambda: False, on_shot=lambda s: None)


# ----------------------------------------------------------------------
# The scan sequence
# ----------------------------------------------------------------------

def test_scan_grid_is_symmetric_raster_and_drops_off_canvas():
    xs, ys, points = scan_grid(10, 1, R=2, step=1, canvas_res=(12, 3))
    assert xs == [8, 9, 10, 11]                 # 12 is off the canvas: dropped, not clamped
    assert ys == [0, 1, 2]                      # -1 dropped
    assert [(p.cx, p.cy) for p in points[:5]] == [(8, 0), (9, 0), (10, 0), (11, 0), (8, 1)]
    assert all(points[i].index == i for i in range(len(points)))
    assert {(p.row, p.col) for p in points} == {(r, c) for r in range(3) for c in range(4)}


def test_every_frame_is_exposed_at_its_own_position_when_the_slm_confirms():
    pattern = SLMPattern()
    rng = random.Random(1)
    slm = FakeSLM(pattern, delay_s=lambda: rng.uniform(0.0, 0.05), confirms=True)
    camera = FakeCamera(pattern)
    _, _, points = scan_grid(100, 200, R=2, step=1, canvas_res=(1920, 1200))

    shots, outcome = run(points, slm, camera, settle_s=0.005)

    assert outcome.startswith("finished")
    assert len(shots) == len(points)
    for s in shots:
        start, end = exposed_at(s)
        assert start == end == (s.point.cx, s.point.cy), s.point
        assert s.slm_applied is True
        assert s.t_slm_applied <= s.t_acquire   # the exposure began after the pattern was up


def test_unconfirmed_slm_is_right_when_settle_covers_the_slm_delay():
    pattern = SLMPattern()
    slm = FakeSLM(pattern, delay_s=0.03, confirms=False)
    camera = FakeCamera(pattern)
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))

    shots, _ = run(points, slm, camera, settle_s=0.08)

    for s in shots:
        assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2
        assert s.slm_applied is None


def test_unconfirmed_slm_is_wrong_when_settle_is_shorter_than_the_slm_delay():
    # Why the GUI warns when the server does not confirm: then nothing but the
    # settle time stands between the send and the exposure.
    pattern = SLMPattern()
    slm = FakeSLM(pattern, delay_s=0.06, confirms=False)
    camera = FakeCamera(pattern)
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))

    shots, _ = run(points, slm, camera, settle_s=0.0)

    assert any(exposed_at(s)[0] != (s.point.cx, s.point.cy) for s in shots)


def test_a_missing_frame_is_none_not_the_previous_frame_and_the_scan_stops():
    pattern = SLMPattern()
    slm = FakeSLM(pattern, delay_s=0.0)
    camera = FakeCamera(pattern, dead=True)
    camera.get_frame_timings = lambda: (0.02, 0.03)
    _, _, points = scan_grid(50, 50, R=2, step=1, canvas_res=(1920, 1200))

    def snap():
        return snap_frame(camera, timeout_s=0.1)

    shots, outcome = run_scan(points, slm.set_center_and_wait, snap, 0.0,
                              should_stop=lambda: False, on_shot=lambda s: None)

    assert len(shots) == scan_group.MAX_CONSECUTIVE_CAMERA_FAILURES
    assert all(s.frame is None and "TimeoutError" in s.error for s in shots)
    assert "no camera frame" in outcome


def test_an_slm_failure_stops_the_scan_before_any_frame_at_that_position():
    pattern = SLMPattern()
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))
    bad = (points[4].cx, points[4].cy)
    slm = FakeSLM(pattern, delay_s=0.0, fail_at=bad)
    camera = FakeCamera(pattern)

    shots, outcome = run(points, slm, camera, settle_s=0.0)

    assert [(s.point.cx, s.point.cy) for s in shots] == [(p.cx, p.cy) for p in points[:4]]
    assert "SLM command failed" in outcome and "connection refused" in outcome


def test_grid_is_filled_by_each_shots_own_row_and_col():
    _, _, points = scan_grid(5, 5, R=1, step=1, canvas_res=(20, 20))
    shots = [scan_group.ScanShot(point=p, frame=np.full((1, 1), p.index), slm_applied=True,
                                 t_slm_sent=0.0, t_slm_applied=0.0, t_acquire=0.0, t_frame=0.0)
             for p in points if p.index != 4]
    random.Random(0).shuffle(shots)

    grid = shots_to_grid(shots, 3, 3)

    assert grid[1][1] is None
    for p in points:
        if p.index != 4:
            assert int(grid[p.row][p.col][0, 0]) == p.index


# ----------------------------------------------------------------------
# SLM wire format
# ----------------------------------------------------------------------

def test_split_commands():
    a, b = '{"center": [1, 2]}', '{"center": [3, 4], "seq": 7}'
    assert split_commands(a + b) == ([a, b], "")                   # joined in one recv
    assert split_commands(a + "\n" + b + "\n") == ([a, b], "")
    assert split_commands(a + b[:9]) == ([a], b[:9])               # split across recvs
    assert split_commands(b[:9], at_eof=True) == ([b[:9]], "")     # never completed
    assert split_commands("10 0.5 1") == (["10 0.5 1"], "")        # legacy plaintext
    assert split_commands("{bad json\n" + a) == (["{bad json", a], "")
    assert command_seq(b) == 7 and command_seq(a) is None
    assert command_seq('{"seq": true}') is None and command_seq("10 0.5 1") is None


@pytest.fixture(scope="module")
def slm_host():
    """run_server's connection handling and SLM worker, with the SLM stubbed."""
    uploads = []

    class StubSLM:
        mask_type = "spot"

        def initialize_slm(self):
            pass

        def generate_mask(self, dimension, phase, center_x, center_y,
                          grating_spacing=10, angle_deg=0, mask=1):
            return (center_x, center_y)

        def fast_upload_to_slm(self, img):
            time.sleep(0.02)
            uploads.append((time.monotonic(), img))

        upload_to_slm = fast_upload_to_slm

    saved = sys.modules.get("slm_server")
    stub = types.ModuleType("slm_server")
    stub.SLM_server = StubSLM
    sys.modules["slm_server"] = stub
    import run_server
    threading.Thread(target=run_server.slm_worker, daemon=True).start()

    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(1)

    def accept_loop():      # run_server.start_server, minus the fixed address
        while True:
            try:
                conn, _ = lsock.accept()
            except OSError:
                return
            run_server.handle_client(conn)

    threading.Thread(target=accept_loop, daemon=True).start()
    yield types.SimpleNamespace(port=lsock.getsockname()[1], uploads=uploads)
    lsock.close()
    run_server.cmd_q.put(None)
    if saved is None:
        sys.modules.pop("slm_server", None)
    else:
        sys.modules["slm_server"] = saved


def wait_for_upload(uploads, center, timeout=2.0):
    t_end = time.monotonic() + timeout
    while True:
        for t, c in list(uploads):
            if tuple(c) == tuple(center):
                return t
        if time.monotonic() >= t_end:
            return None
        time.sleep(0.005)


def test_controller_waits_for_the_server_to_apply(slm_host):
    slm = SLMController(server_ip="127.0.0.1", server_port=slm_host.port)
    try:
        r = slm.set_center_and_wait(321, 432)
        assert r.ok and r.applied is True, r.error
        assert slm.server_replies is True
        t_upload = wait_for_upload(slm_host.uploads, (321, 432), timeout=0.0)
        assert t_upload is not None and t_upload <= r.t_applied
        assert r.server_apply_s is not None and r.server_apply_s >= 0.02
    finally:
        slm.close()


def test_server_takes_joined_split_and_unterminated_commands(slm_host):
    cmds = [json.dumps({"mask": "spot", "center": [c, c + 1], "dimension": 10})
            for c in (11, 12, 13)]
    with socket.create_connection(("127.0.0.1", slm_host.port)) as s:
        s.sendall((cmds[0] + cmds[1]).encode())          # two in one segment
        time.sleep(0.05)
        s.sendall(cmds[2][:10].encode())                 # one split in two
        time.sleep(0.05)
        s.sendall(cmds[2][10:].encode())
    # the way waxx.control.slm.SLM sends: no newline, then close
    with socket.create_connection(("127.0.0.1", slm_host.port)) as s:
        s.sendall(json.dumps({"mask": "spot", "center": [14, 15], "dimension": 10}).encode())

    times = [wait_for_upload(slm_host.uploads, (c, c + 1)) for c in (11, 12, 13, 14)]
    assert None not in times
    assert times == sorted(times)


def test_controller_falls_back_once_for_a_server_that_never_replies():
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(4)

    def old_server():   # reads commands, never answers -- the old run_server.py
        while True:
            try:
                conn, _ = lsock.accept()
            except OSError:
                return
            with conn:
                while conn.recv(1024):
                    pass

    threading.Thread(target=old_server, daemon=True).start()
    slm = SLMController(server_ip="127.0.0.1", server_port=lsock.getsockname()[1])
    try:
        t0 = time.monotonic()
        first = slm.set_center_and_wait(10, 10)
        t1 = time.monotonic()
        second = slm.set_center_and_wait(11, 10)
        t2 = time.monotonic()
        assert first.ok and first.applied is None
        assert slm.server_replies is False
        # (Windows socket timeouts can fire a fraction of a millisecond early)
        assert slm_group.RECEIPT_TIMEOUT_S - 0.05 <= t1 - t0 < slm_group.RECEIPT_TIMEOUT_S + 1.0
        assert second.ok and second.applied is None and t2 - t1 < 0.5
    finally:
        slm.close()
        lsock.close()


def test_controller_reports_an_unreachable_server():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                       # nothing listens there now
    slm = SLMController(server_ip="127.0.0.1", server_port=port)
    try:
        r = slm.set_center_and_wait(10, 10)
        assert not r.ok and r.error
    finally:
        slm.close()


# ----------------------------------------------------------------------
# The window: scan wiring, camera release, stage buttons
# ----------------------------------------------------------------------

class FakeStage:
    calls = []
    connected = True

    def __init__(self, discovery_timeout=3.0, raise_on_error=True):
        self._position = "out"

    def position(self):
        FakeStage.calls.append("position")
        return self._position

    def move_to(self, state, force=False):
        FakeStage.calls.append(("move_to", state, force))
        self._position = state
        return f"moved {state}"


@pytest.fixture
def app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def process_until(app, cond, timeout=10.0):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


def build_window(slm_host, monkeypatch, camera, **kwargs):
    """The spot finder window, with the stage, the SLM server and liveOD's
    run state all fakes. Close it, then stop ``w._test_gate``."""
    import stage_group
    import SLM_andor_main_gui as main_gui
    FakeStage.calls = []
    monkeypatch.setattr(stage_group, "APDStageClient", FakeStage)
    monkeypatch.setattr(main_gui.FinalScanPreviewDialog, "exec", lambda self: 0)
    # never the lab SLM PC, not even for the startup reachability probe
    monkeypatch.setattr(main_gui, "SLMController", lambda canvas_res, **kw: SLMController(
        canvas_res=canvas_res, server_ip="127.0.0.1", server_port=slm_host.port,
        **{k: v for k, v in kw.items() if k == "write_gate"}))
    gate, liveod = None, None
    if HAS_SEAM:
        # never the lab liveOD either: the run state is a dict the test sets
        from run_gate import RunGate
        liveod = {"ok": True, "run_in_progress": False, "run_id": 80712}
        gate = RunGate(status_fn=lambda: dict(liveod), poll_period_s=0.02)
        kwargs["run_gate"] = gate
    w = main_gui.UnifiedControlGUI(camera, **kwargs)
    w._test_liveod = liveod
    w._test_gate = gate
    return w


def close_window(w):
    w.close()
    if w._test_gate is not None:
        w._test_gate.stop()


@pytest.fixture
def gui(app, slm_host, monkeypatch):
    pattern = SLMPattern()
    camera = FakeCamera(pattern)
    w = build_window(slm_host, monkeypatch, camera, connect_camera_on_start=False)
    w._test_pattern = pattern
    if HAS_SEAM:
        assert process_until(app, lambda: w._gate_open)
    yield w
    close_window(w)


def test_window_scan_files_each_frame_under_its_position(app, gui, slm_host):
    # The fake camera looks at the pattern the stubbed server last uploaded.
    gui._test_pattern.get = lambda: tuple(slm_host.uploads[-1][1])
    shots_seen = []
    gui.scan_R_sb.setValue(1)
    gui.settle_sb.setValue(10)
    gui.start_scan()
    gui.scan_worker.finished_sig.connect(lambda shots, outcome: shots_seen.append((shots, outcome)))
    assert gui._scanning and not gui.scan_btn.isEnabled() and not gui.stage_group.out_btn.isEnabled()
    assert gui.camera_pill.state == "grabbing"

    assert process_until(app, lambda: not gui._scanning)
    shots, outcome = shots_seen[0]
    assert outcome.startswith("finished") and len(shots) == 9
    for s in shots:
        assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2
        assert s.slm_applied is True
    assert gui.scan_btn.isEnabled() and gui.stage_group.out_btn.isEnabled()


def test_arrow_keys_nudge_the_spot_through_the_scrolling_sidebar(app, gui):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    gui.show()
    x0, y0 = gui.slm.get_center()
    # From a sidebar widget that does not use arrow keys itself, the key climbs
    # through the scroll area, which must pass it on. (A focused push button
    # takes all four arrows to move focus -- Qt's own, and so before this too.)
    QTest.keyClick(gui.scan_progress, Qt.Key.Key_Down)
    assert gui.slm.get_center() == (x0, y0 + 5)
    QTest.keyClick(gui, Qt.Key.Key_Right)
    assert gui.slm.get_center() == (x0 + 5, y0 + 5)
    assert gui.minimumSizeHint().height() < 700            # scrolls instead of growing

    gui._scanning = True                                     # the scan owns the pattern
    QTest.keyClick(gui, Qt.Key.Key_Right)
    QTest.keyClick(gui.scan_progress, Qt.Key.Key_Down)
    assert gui.slm.get_center() == (x0 + 5, y0 + 5)
    gui._scanning = False


def test_window_releases_and_reconnects_nothing_moves_the_stage(app, gui, monkeypatch):
    import SLM_andor_main_gui as main_gui
    camera = gui.camera
    assert process_until(app, lambda: gui.stage_group.stage is not None)
    assert gui.stage_group.position == "out"
    assert not any(c[0] == "move_to" for c in FakeStage.calls if isinstance(c, tuple))

    gui.camera_pill.click()                       # disconnect
    assert process_until(app, lambda: not gui._camera_connected())
    assert camera.closed and gui.camera_pill.state == "closed"
    assert not gui.scan_btn.isEnabled()

    reopened = FakeCamera(SLMPattern())
    monkeypatch.setattr(main_gui, "AndorEMCCD", lambda **kw: reopened)
    gui.camera_pill.click()                       # connect again, same window
    assert process_until(app, lambda: gui.camera is reopened)
    assert gui.camera_pill.state == "open" and gui.scan_btn.isEnabled()

    gui.stage_group.in_btn.click()
    assert process_until(app, lambda: gui.stage_group.position == "in")
    assert ("move_to", "in", False) in FakeStage.calls


# ----------------------------------------------------------------------
# Runs: the run gate, a run taking the camera, the FrameSource seam
# ----------------------------------------------------------------------

RUN_REASON = "run 80713 in progress -- SLM writes blocked during runs"


class CountingSLM(FakeSLM):
    """FakeSLM that records every set_center_and_wait, i.e. every SLM write."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def set_center_and_wait(self, cx, cy):
        self.calls.append((cx, cy))
        return super().set_center_and_wait(cx, cy)


class FakeGate:
    """A write gate: open for the first ``n_open`` checks, closed after."""

    def __init__(self, n_open=0, reason=RUN_REASON):
        self.n_open = n_open
        self.reason = reason
        self.calls = 0

    def check(self):
        self.calls += 1
        if self.calls <= self.n_open:
            return True, ""
        return False, self.reason


def controller_state(slm):
    return (slm.mode, tuple(slm.spot_center), slm.spot_radius, tuple(slm.grating_center),
            slm.grating_size, slm.grating_spacing, slm.angle_deg)


def wait_until(cond, timeout=2.0):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        if cond():
            return True
        time.sleep(0.005)
    return False


@needs_seam
def test_preempted_snap_stops_scan_before_next_slm_write():
    from frame_source import Preempted
    pattern = SLMPattern()
    slm = CountingSLM(pattern, delay_s=0.0)
    camera = FakeCamera(pattern)
    timeout = scan_group.frame_timeout_s(camera)
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))
    k = 4           # snaps before the run takes the camera
    n_snaps = []

    def snap():
        if len(n_snaps) == k:
            raise Preempted("run armed the camera", run_tag="80713")
        n_snaps.append(1)
        return snap_frame(camera, timeout)

    filed = []
    shots, outcome = run_scan(points, slm.set_center_and_wait, snap, 0.0,
                              should_stop=lambda: False, on_shot=filed.append)

    # the position in flight was written; nothing after it
    assert slm.calls == [(p.cx, p.cy) for p in points[:k + 1]]
    assert len(shots) == k and filed == shots
    # ... and it is not filed: blank ("not reached"), not a red X
    assert all(s.frame is not None and not s.error for s in shots)
    assert shots_to_grid(shots, 3, 3)[points[k].row][points[k].col] is None
    assert "camera taken by run 80713" in outcome
    assert f"({points[k].cx}, {points[k].cy})" in outcome
    assert f"{k}/{len(points)} done" in outcome


@needs_seam
def test_gate_checked_before_every_slm_write():
    pattern = SLMPattern()
    slm = CountingSLM(pattern, delay_s=0.0)
    camera = FakeCamera(pattern)
    timeout = scan_group.frame_timeout_s(camera)
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))
    log = []

    def set_center(cx, cy):
        log.append("write")
        return slm.set_center_and_wait(cx, cy)

    def may_write():            # a run starts after the 3rd position
        log.append("gate")
        return (True, "") if log.count("write") < 3 else (False, RUN_REASON)

    shots, outcome = run_scan(points, set_center, lambda: snap_frame(camera, timeout), 0.0,
                              should_stop=lambda: False, on_shot=lambda s: None,
                              may_write=may_write)

    assert log == ["gate", "write"] * 3 + ["gate"]      # asked before every write
    assert len(slm.calls) == 3 and len(shots) == 3       # no 4th write
    assert RUN_REASON in outcome and f"3/{len(points)} done" in outcome
    assert f"({points[3].cx}, {points[3].cy})" in outcome


@needs_seam
def test_slm_controller_refuses_all_writes_when_gate_closed(app, slm_host):
    uploads = slm_host.uploads
    slm = SLMController(server_ip="127.0.0.1", server_port=slm_host.port,
                        write_gate=FakeGate(n_open=0))
    blocked, changed = [], []
    slm.blocked.connect(blocked.append)
    slm.state_changed.connect(lambda: changed.append(1))
    try:
        n0 = len(uploads)
        before = controller_state(slm)
        slm.set_center(5, 6)
        slm.nudge_center(1, 1)
        slm.reset_center_to_default()
        slm.set_spot_radius(33)
        slm.set_mode("grating")
        slm.set_grating_size(50)
        slm.set_grating_spacing(9)
        slm.set_angle_deg(12.0)
        slm.send_update()
        slm.resend()
        r = slm.set_center_and_wait(7, 8)
        app.processEvents()

        assert not r.ok and r.blocked and r.error == RUN_REASON
        assert controller_state(slm) == before and not changed
        assert len(blocked) == 11 and set(blocked) == {RUN_REASON}
        # a link probe sends no pattern, and still goes through
        slm.check_link()
        assert process_until(app, lambda: slm._last_link is not None)
        assert slm._last_link[0] == "open"
        time.sleep(0.2)                         # the stub takes 20 ms per upload
        assert len(uploads) == n0
    finally:
        slm.close()

    # A run that starts between the setter's check and the send: the sender
    # asks again and drops the command, and the SLM state is marked unknown.
    slm = SLMController(server_ip="127.0.0.1", server_port=slm_host.port,
                        write_gate=FakeGate(n_open=1))
    try:
        n0 = len(uploads)
        slm.set_center(600, 700)
        assert slm.get_center() == (600, 700)          # the setter was let through
        assert wait_until(lambda: slm.unknown_reason != "")
        assert "(600, 700) was not sent" in slm.unknown_reason
        assert RUN_REASON in slm.unknown_reason
        time.sleep(0.2)
        assert len(uploads) == n0
    finally:
        slm.close()


@needs_seam
def test_return_to_start_and_tile_pick_blocked_during_run(app, gui, slm_host):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    uploads = slm_host.uploads
    x0, y0 = gui.slm.get_center()
    gui._scan_start_center = (x0, y0)       # as a finished scan leaves it ...
    n = len(uploads)
    gui.slm.set_center(x0 + 7, y0)          # ... with the pattern parked elsewhere
    assert process_until(app, lambda: any(tuple(c) == (x0 + 7, y0) for _, c in uploads[n:]))
    gui._update_controls()
    assert gui.return_btn.isEnabled()
    assert process_until(app, lambda: gui.slm_sync_row.isHidden())   # the SLM has it

    gui._test_liveod.update(run_in_progress=True, run_id=80713)
    assert process_until(app, lambda: not gui.return_btn.isEnabled())
    assert not gui.run_banner.isHidden() and "80713 in progress" in gui.run_banner.text()
    assert not gui.scan_btn.isEnabled() and not gui.resend_btn.isEnabled()
    assert not gui.slm_preview.isEnabled()
    assert not any(grp.isEnabled() for grp in gui._pattern_groups)
    assert not gui.slm_sync_row.isHidden() and "run 80713" in gui.slm_sync_label.text()

    n = len(uploads)
    radius = gui.slm.spot_radius
    gui.return_btn.click()                   # disabled: does nothing
    gui.on_return_to_start()                 # and refuses if reached anyway
    gui.on_scan_spot_picked(x0 - 3, y0 + 2)  # a tile pick in the scan preview
    gui._on_preview_dragged(10, 10)
    gui.on_resend()
    QTest.keyClick(gui, Qt.Key.Key_Left)
    gui.mode_grating_rb.setChecked(True)     # through the controller: refused ...
    gui.radius_sb.setValue(radius + 20)
    app.processEvents()
    assert gui.mode_spot_rb.isChecked() and gui.slm.mode == "spot"   # ... and put back
    assert gui.radius_sb.value() == radius == gui.slm.spot_radius
    time.sleep(0.2)
    app.processEvents()
    assert len(uploads) == n
    assert gui.slm.get_center() == (x0 + 7, y0)

    gui._test_liveod.update(run_in_progress=False)
    assert process_until(app, lambda: gui.return_btn.isEnabled())
    assert gui.run_banner.isHidden() and gui.resend_btn.isEnabled()
    time.sleep(0.2)
    app.processEvents()
    assert len(uploads) == n                              # nothing sent on its own
    assert "run 80713" in gui.slm_sync_label.text() and not gui.slm_sync_row.isHidden()

    gui.return_btn.click()
    assert process_until(app, lambda: any(tuple(c) == (x0, y0) for _, c in uploads[n:]))
    assert process_until(app, lambda: gui.slm_sync_row.isHidden())


@needs_seam
def test_run_gate_fails_closed_on_stale_or_unreachable():
    from run_gate import RunGate
    now = [100.0]
    replies = []

    def status():
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r() if callable(r) else r

    def slow_reply():               # liveOD's REP loop busy: the answer is late
        now[0] += 2.5
        return {"ok": True, "run_in_progress": False, "run_id": 80713}

    gate = RunGate(status_fn=status, max_age_s=2.0, clock=lambda: now[0],
                   wall_clock=lambda: now[0])

    ok, reason = gate.check()                                   # never polled
    assert not ok and "liveOD unreachable" in reason and "no reply yet" in reason

    replies.append(ConnectionError("no response from liveOD"))
    assert not gate.poll_once()
    ok, reason = gate.check()
    assert not ok and "liveOD unreachable" in reason and "ConnectionError" in reason

    replies.append({"ok": True, "run_in_progress": False, "run_id": 80712})
    assert gate.poll_once() and gate.check() == (True, "")

    replies.append({"ok": True, "run_id": 80712})              # does not say: not "no run"
    assert not gate.poll_once()
    ok, reason = gate.check()
    assert not ok and "run_in_progress" in reason

    replies.append({"ok": True, "run_in_progress": False, "run_id": 80712})
    assert gate.poll_once() and gate.check()[0]
    now[0] += 2.5                                               # no answer since
    ok, reason = gate.check()
    assert not ok and "no run state for 2.5 s (limit 2.0 s)" in reason

    replies.append({"ok": True, "run_in_progress": True, "run_id": 80713})
    assert gate.poll_once()
    assert gate.check() == (False, RUN_REASON)
    assert gate.snapshot()["runs_seen"] == 1 and gate.snapshot()["last_run_id"] == 80713

    replies.append(slow_reply)                     # timed from the send: stale on arrival
    assert gate.poll_once()
    ok, reason = gate.check()
    assert not ok and "liveOD unreachable" in reason

    # a run that came and went between two polls still counts as seen
    replies.append({"ok": True, "run_in_progress": False, "run_id": 80714})
    assert gate.poll_once() and gate.check() == (True, "")
    assert gate.snapshot()["runs_seen"] == 2 and gate.snapshot()["last_run_id"] == 80714

    # On its own thread: a poll that hangs closes the gate by age, and check()
    # never waits for the poll.
    busy, release = threading.Event(), threading.Event()

    def hanging_status():
        if busy.is_set():
            release.wait(5.0)
        return {"ok": True, "run_in_progress": False, "run_id": 1}

    threaded = RunGate(status_fn=hanging_status, max_age_s=0.3, poll_period_s=0.02).start()
    try:
        assert wait_until(lambda: threaded.check()[0])
        busy.set()
        assert wait_until(lambda: not threaded.check()[0])
        t0 = time.monotonic()
        ok, reason = threaded.check()
        assert time.monotonic() - t0 < 0.05
        assert not ok and "liveOD unreachable" in reason and "limit 0.3 s" in reason
    finally:
        release.set()
        threaded.stop()


@needs_seam
def test_liveod_status_passes_poll_through_and_drops_a_broken_client():
    # The default status_fn, with a fake client in place of LiveODClient (no network).
    from run_gate import LiveODStatus, RunGate

    class FakeClient:
        def __init__(self, replies):
            self.replies, self.closed = list(replies), False

        def poll(self):
            r = self.replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        def close(self):
            self.closed = True

    status = LiveODStatus()
    client = FakeClient([{"ok": True, "run_in_progress": True, "run_id": 80713},
                         {"ok": False, "error": "busy"},
                         ConnectionError("no response"),
                         OSError("socket in a bad state")])
    status._client = client
    gate = RunGate(status_fn=status)
    assert gate.poll_once() and gate.check() == (False, RUN_REASON)
    assert not gate.poll_once() and "refused POLL" in gate.check()[1]
    assert not gate.poll_once() and "ConnectionError" in gate.check()[1]
    assert status._client is client            # a timeout: the client reconnects itself
    assert not gate.poll_once() and "OSError" in gate.check()[1]
    assert status._client is None and client.closed    # anything else: rebuilt next poll


@needs_seam
def test_legacy_copies_refuse_to_run(monkeypatch):
    # The old test/ GUIs write the SLM with no run gate. They must refuse at
    # build(), before they would open the camera (stubbed to fail loudly here).
    import importlib.util
    from artiq.language.environment import EnvExperiment

    def no_camera(*args, **kwargs):
        raise AssertionError("the legacy copy tried to open the camera")

    legacy = sorted((SPOT_FINDER / "test").glob("*.py"))
    assert legacy
    for path in legacy:
        spec = importlib.util.spec_from_file_location(f"legacy_spot_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        monkeypatch.setattr(mod, "AndorEMCCD", no_camera)
        expts = [c for c in vars(mod).values() if isinstance(c, type)
                 and issubclass(c, EnvExperiment) and c is not EnvExperiment]
        assert expts, path.name
        for cls in expts:
            with pytest.raises(RuntimeError, match="superseded -- use the main spot finder GUI"):
                cls.build(object.__new__(cls))


@needs_seam
def test_window_video_runs_through_the_source(app, gui):
    frames = []
    gui._frame_sig.connect(frames.append)
    gui.video_btn.click()
    assert gui.video_btn.isChecked() and gui.source.video_running()
    assert process_until(app, lambda: len(frames) >= 3)
    assert gui.camera_pill.state == "grabbing"
    gui.video_btn.click()
    assert process_until(app, lambda: not gui.source.video_running())
    assert not gui.video_btn.isChecked() and gui.camera_pill.state == "open"


@needs_seam
def test_local_source_preserves_snap_semantics(app):
    from frame_source import LocalAndorSource
    pattern = SLMPattern()
    rng = random.Random(2)
    slm = FakeSLM(pattern, delay_s=lambda: rng.uniform(0.0, 0.05), confirms=True)
    camera = FakeCamera(pattern)
    source = LocalAndorSource(camera)
    assert source.is_open() and source.camera is camera
    assert not LocalAndorSource(None).is_open()
    assert scan_group.frame_timeout_s(source) == scan_group.frame_timeout_s(camera)
    _, _, points = scan_grid(100, 200, R=2, step=1, canvas_res=(1920, 1200))
    timeout = scan_group.frame_timeout_s(source)

    shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: source.snap(timeout),
                              0.005, should_stop=lambda: False, on_shot=lambda s: None)

    assert outcome.startswith("finished") and len(shots) == len(points)
    for s in shots:
        start, end = exposed_at(s)
        assert start == end == (s.point.cx, s.point.cy), s.point
        assert s.slm_applied is True
        assert s.t_slm_applied <= s.t_acquire

    # the ScanWorker, which owns the source for the scan, run on this thread
    got = []
    worker = scan_group.ScanWorker(slm, source, points[:3], settle_s=0.005)
    worker.finished_sig.connect(lambda shots, outcome: got.append((shots, outcome)))
    worker.run()
    app.processEvents()
    shots, outcome = got[0]
    assert outcome.startswith("finished")
    assert [exposed_at(s) for s in shots] == [((p.cx, p.cy),) * 2 for p in points[:3]]

    source.close()
    assert camera.closed and not source.is_open()


# ----------------------------------------------------------------------
# liveOD's camera host: StreamSource against a real CameraServerCore
# ----------------------------------------------------------------------

try:
    from beacon.camera.backend import RawFrame
    from beacon.camera.core import CameraServerCore
    from beacon.camera.directory import CameraDirectory, CameraEntry
    from beacon.camera.fake_backend import FakeBackend
    from beacon.discovery.server import NetServer
except ImportError:                     # no beacon: the StreamSource tests skip
    CameraServerCore = FakeBackend = None

HAS_STREAM = (HAS_SEAM and CameraServerCore is not None
              and "class StreamSource" in (SPOT_FINDER / "frame_source.py").read_text(
                  encoding="utf-8"))
needs_stream = pytest.mark.skipif(
    not HAS_STREAM, reason=f"{SPOT_FINDER} has no StreamSource (or beacon is missing)")

HOST_ID = "camera_server:spot-test:liveod"      # never beaconed (QuietCore)
ANDOR_ID = "andor_emccd:SPOT0001"
MODE_CODE = {"live": 1, "snap": 2, "run": 3}
RUN_VALUES = {"trigger_mode": "ext", "exposure_time": 1e-3, "gain": 1, "shutter": "open"}


if FakeBackend is not None:
    class PatternBackend(FakeBackend):
        """FakeBackend as liveOD's Andor, whose frames say what the SLM showed.

        Row 0 of a frame is [x_start, y_start, x_end, y_end] -- the SLMPattern
        when its exposure started and ended, as FakeCamera's -- and row 1 starts
        with 1 / 2 / 3 for a live / snap / run frame. An exposure starts at
        start_acquisition() or right after the previous frame, and ends when the
        frame is made: one cycle later, or at a trigger() edge in a run.
        """

        def __init__(self, pattern, cycle_s=0.02):
            super().__init__(
                ANDOR_ID, "andor_emccd", shape=(2, 4), cycle_s=cycle_s, model="FakeEMCCD",
                settings={"exposure_time": cycle_s, "cycle_time": cycle_s, "gain": 1,
                          "trigger_mode": "int", "shutter": "open"},
                ranges={"exposure_time": (1e-5, 10.0), "gain": (1, 300)},
                choices={"trigger_mode": ("int", "software", "ext"),
                         "shutter": ("open", "closed")})
            self.pattern = pattern
            self._exp_start = None

        def start_acquisition(self, mode, n_frames=None):
            self._exp_start = self.pattern.get()
            super().start_acquisition(mode, n_frames)

        def _produce(self):             # FakeBackend._produce, with the pattern in the pixels
            mode = self._mode
            idx = self._produced
            self._produced += 1
            end = self.pattern.get()
            start = end if self._exp_start is None else self._exp_start
            self._exp_start = end
            img = np.zeros(self.shape, dtype=np.uint16)
            img[0] = [*start, *end]
            img[1, 0] = MODE_CODE.get(mode, 0)
            self._pending.append(RawFrame(img, hw_idx=idx, hw_ts=idx, t_host=time.time()))
            if self._n_max is not None and self._produced >= self._n_max:
                self._mode = None

    class QuietCore(CameraServerCore):
        """A CameraServerCore that never beacons, whatever NetServer does."""

        def _start_beacon(self):
            pass


class NoAliases:
    """The directory's alias store: none (never this PC's real one)."""

    def all(self):
        return {}


class Host:
    """liveOD's camera host, as far as the spot finder can tell: a real
    CameraServerCore (policy "persistent") on 127.0.0.1 serving one fake Andor,
    open and streaming, found through directories whose discovery is ``addr``."""

    def __init__(self, pattern, state_dir):
        self.pattern = pattern
        self.state_dir = str(state_dir)
        self.addr = {}
        self.core = self.backend = None
        self._dirs, self._sources = [], []
        self.start()

    def start(self, live=True):
        core = QuietCore(HOST_ID, policy="persistent", bind_host="127.0.0.1",
                         check_duplicate=False, state_dir=self.state_dir)
        backend = PatternBackend(self.pattern)
        core.add_camera(ANDOR_ID, lambda: backend, category="andor_emccd", owner_key="andor",
                        info={"model": "FakeEMCCD"})
        core.start_in_thread()
        assert core._waxx_beacon_thread is None         # nothing was broadcast
        w = core.worker(ANDOR_ID)
        w.call("open", 5.0)                              # liveOD claims it at startup
        if live:
            w.call("start_live", 5.0)
        self.core, self.backend = core, backend
        self.addr.clear()
        self.addr[HOST_ID] = ("127.0.0.1", core.port)

    def stop(self):
        if self.core is not None:
            self.core.stop(10)

    def restart(self):
        self.stop()
        self.start()

    @property
    def worker(self):
        return self.core.worker(ANDOR_ID)

    def directory(self):
        d = CameraDirectory(collect_for=0.0, request_timeout_s=1.0, store=NoAliases(),
                            discover=lambda prefix: (dict(self.addr)
                                                     if prefix == "camera_server:" else {}))
        self._dirs.append(d)
        return d

    def open_source(self, **kw):
        """A StreamSource on this host, attached; no status thread unless asked."""
        from frame_source import StreamSource
        kw.setdefault("status_poll_s", None)
        kw.setdefault("timeout_s", 1.0)
        src = StreamSource(ANDOR_ID, label="spot finder test", directory=self.directory(), **kw)
        self._sources.append(src)
        src.open()
        return src

    def take_camera_for_run(self, tag="80713", n_frames=2, trigger=True):
        """What liveOD does at INIT_RUN / WAIT_CAM_READY, then the kernel's triggers."""
        w = self.worker
        w.call("lock", 5.0, token="RUN", reason=f"run {tag}")
        w.call("arm", 5.0, token="RUN", values=dict(RUN_VALUES), n_frames=n_frames, run_tag=tag)
        if trigger:
            self.backend.trigger(n_frames)

    def end_run(self):
        w = self.worker
        w.call("disarm", 5.0, token="RUN")
        w.call("unlock", 5.0, token="RUN")

    def close(self):
        for s in self._sources:
            try:
                s.close()
            except Exception:
                pass
        self.stop()
        for d in self._dirs:
            d.close()


@pytest.fixture
def host(monkeypatch, tmp_path):
    monkeypatch.setenv("BEACON_STATE_DIR", str(tmp_path / "beacon_state"))
    # with QuietCore, twice over: no NetServer in this test broadcasts anything
    monkeypatch.setattr(NetServer, "_start_beacon", lambda self: None)
    h = Host(SLMPattern(), tmp_path)
    yield h
    h.close()


def mode_of(frame):
    return int(frame[1, 0])


@needs_stream
def test_scan_through_host_files_each_frame_under_its_position(app, host):
    rng = random.Random(3)
    slm = FakeSLM(host.pattern, delay_s=lambda: rng.uniform(0.0, 0.05), confirms=True)
    source = host.open_source()
    _, _, points = scan_grid(100, 200, R=2, step=1, canvas_res=(1920, 1200))

    source.begin_scan()
    timeout = scan_group.frame_timeout_s(source)
    assert timeout == pytest.approx(2 * 0.02 + 2.0)     # from the host's cycle_time
    shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: source.snap(timeout),
                              0.005, should_stop=lambda: False, on_shot=lambda s: None)
    source.end_scan()

    assert outcome.startswith("finished") and len(shots) == len(points)
    for s in shots:
        start, end = exposed_at(s)
        assert start == end == (s.point.cx, s.point.cy), s.point
        assert mode_of(s.frame) == MODE_CODE["snap"]
        assert s.slm_applied is True
        assert s.t_slm_applied <= s.t_acquire

    # the ScanWorker, which owns the source for the scan, run on this thread
    got = []
    worker = scan_group.ScanWorker(slm, source, points[:3], settle_s=0.005)
    worker.finished_sig.connect(lambda shots, outcome: got.append((shots, outcome)))
    worker.run()
    app.processEvents()
    shots, outcome = got[0]
    assert outcome.startswith("finished")
    assert [exposed_at(s) for s in shots] == [((p.cx, p.cy),) * 2 for p in points[:3]]

    # detaching leaves liveOD's camera open, and streaming again after the snaps
    source.close()
    assert host.worker.is_open and host.worker.state == "streaming"


@needs_stream
def test_run_arming_mid_scan_preempts_and_no_run_frame_is_filed(host):
    from run_gate import CombinedGate
    slm = CountingSLM(host.pattern, delay_s=0.0)
    source = host.open_source()
    _, _, points = scan_grid(100, 200, R=5, step=1, canvas_res=(1920, 1200))
    filed = []

    source.begin_scan()
    timeout = scan_group.frame_timeout_s(source)
    timer = threading.Timer(0.4, host.take_camera_for_run)     # lock + arm + triggers
    timer.start()
    try:
        shots, outcome = run_scan(points, slm.set_center_and_wait,
                                  lambda: source.snap(timeout), 0.01,
                                  should_stop=lambda: False, on_shot=filed.append)
    finally:
        timer.join()
    n_writes = len(slm.calls)

    assert 0 < len(shots) < len(points)
    assert "camera taken by" in outcome, outcome
    assert filed == shots
    for s in shots:                     # only snaps, each at its own position
        assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2
        assert mode_of(s.frame) == MODE_CODE["snap"]
    # one SLM write per filed position, the one in flight, and none after
    assert slm.calls[:len(shots)] == [(s.point.cx, s.point.cy) for s in shots]
    assert len(shots) <= n_writes <= len(shots) + 1
    time.sleep(0.3)
    assert len(slm.calls) == n_writes
    # the run did take frames -- none of them was filed
    assert wait_until(lambda: host.worker.slot.latest(sources=("run",)) is not None)
    assert host.worker.slot.latest(sources=("run",)).run_tag == "80713"

    # the source's own gate: closed after the preemption, and while the run holds it
    ok, reason = source.check()
    assert not ok and "took liveOD's Andor" in reason
    assert source.poll_status()
    ok, reason = source.check()
    assert not ok and "run 80713 holds liveOD's Andor" in reason
    assert CombinedGate(lambda: (True, ""), lambda: source).check() == (False, reason)
    host.end_run()
    assert source.poll_status() and source.check() == (True, "")
    snap = source.gate_snapshot()
    assert snap["runs_seen"] == 1 and snap["last_run_tag"] == "80713"


@needs_stream
@pytest.mark.parametrize("spoil", ["run", "stale", "foreign_snap", "foreign_camera"])
def test_snap_rejects_run_stale_or_foreign_frames(host, monkeypatch, spoil):
    import dataclasses
    from beacon.camera.stream import SnapMismatch
    change = {"run": dict(source="run", run_tag="80713"),
              "stale": dict(seq=0),
              "foreign_snap": dict(snap_id="someone-elses-snap"),
              "foreign_camera": dict(camera_id="andor_emccd:OTHER")}[spoil]
    slot = host.worker.slot
    real_latest = slot.latest

    def latest(sources=("live", "snap"), after_seq=None, snap_id=None):
        f = real_latest(sources=sources, after_seq=after_seq, snap_id=snap_id)
        if f is not None and snap_id is not None:        # the snap's own frame, spoiled
            f = dataclasses.replace(f, **change)
        return f

    monkeypatch.setattr(slot, "latest", latest)          # the core hands out what this gives
    source = host.open_source()
    source.begin_scan()
    with pytest.raises(SnapMismatch):
        source.snap(3.0)

    # in a scan: never filed -- a missing frame (red X) -- and three in a row stop it
    slm = CountingSLM(host.pattern, delay_s=0.0)
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))
    shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: source.snap(3.0), 0.0,
                              should_stop=lambda: False, on_shot=lambda s: None)
    assert len(shots) == scan_group.MAX_CONSECUTIVE_CAMERA_FAILURES
    assert all(s.frame is None and "SnapMismatch" in s.error for s in shots)
    assert "no camera frame" in outcome


@needs_stream
def test_settings_changed_by_another_client_stop_the_scan(host):
    other = host.open_source()                           # another program on this PC
    k = 3

    class ChangingSLM(CountingSLM):
        def set_center_and_wait(self, cx, cy):
            r = super().set_center_and_wait(cx, cy)
            if len(self.calls) == k:
                ok, msg = other.apply(0.03, 7)           # mid-scan, before this snap
                assert ok, msg
            return r

    slm = ChangingSLM(host.pattern, delay_s=0.0)
    source = host.open_source()
    source.begin_scan()
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))

    shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: source.snap(3.0), 0.0,
                              should_stop=lambda: False, on_shot=lambda s: None)

    assert len(shots) == k - 1 and len(slm.calls) == k   # the position in flight, no more
    assert "camera settings changed by another program" in outcome
    assert "settings_rev" in outcome


@needs_stream
def test_scan_after_a_run_takes_the_hosts_live_restore_at_its_first_snap(host, monkeypatch):
    # liveOD's host leaves the camera at a run's settings and puts the live
    # profile back before the next remote SNAP (HostServerCore.before_snap):
    # the revision moves once, at the scan's first frame, and the scan goes on.
    w = host.worker
    real_h_snap = host.core._v2_handlers["SNAP"]
    restored = []

    def h_snap(req):
        if not restored:
            restored.append(w.settings_rev)
            w.submit("apply", values={}, purpose="live")
        return real_h_snap(req)

    monkeypatch.setitem(host.core._v2_handlers, "SNAP", h_snap)
    slm = FakeSLM(host.pattern, delay_s=0.0)
    source = host.open_source()
    source.begin_scan()
    rev0 = w.settings_rev
    _, _, points = scan_grid(50, 50, R=1, step=1, canvas_res=(1920, 1200))

    shots, outcome = run_scan(points, slm.set_center_and_wait, lambda: source.snap(3.0), 0.0,
                              should_stop=lambda: False, on_shot=lambda s: None)

    assert outcome.startswith("finished") and len(shots) == len(points), outcome
    assert restored == [rev0] and w.settings_rev == rev0 + 1
    for s in shots:
        assert exposed_at(s) == ((s.point.cx, s.point.cy),) * 2


@needs_stream
def test_host_restart_mid_scan_raises_server_restarted_and_closes_gate(host):
    from frame_source import ServerRestarted
    from run_gate import CombinedGate
    k = 4

    class RestartingSLM(CountingSLM):
        def set_center_and_wait(self, cx, cy):
            r = super().set_center_and_wait(cx, cy)
            if len(self.calls) == k:
                host.restart()      # liveOD restarts between this SLM write and its snap
            return r

    slm = RestartingSLM(host.pattern, delay_s=0.0)
    source = host.open_source()
    old_instance = host.core.instance
    raised = []

    def snap():
        try:
            return source.snap(3.0)
        except Exception as e:
            raised.append(e)
            raise

    source.begin_scan()
    _, _, points = scan_grid(50, 50, R=2, step=1, canvas_res=(1920, 1200))
    shots, outcome = run_scan(points, slm.set_center_and_wait, snap, 0.0,
                              should_stop=lambda: False, on_shot=lambda s: None)

    assert len(shots) == k - 1 and len(slm.calls) == k
    assert all(s.frame is not None for s in shots)
    assert isinstance(raised[-1], ServerRestarted)
    assert raised[-1].old_instance == old_instance
    assert raised[-1].new_instance == host.core.instance != old_instance
    assert "camera host restarted" in outcome and f"{k - 1}/{len(points)} done" in outcome

    # The gate closes: no SLM write until the new host has said whether a run
    # holds the camera -- and the restart is counted, for "SLM state unknown".
    ok, reason = source.check()
    assert not ok and "restarted" in reason
    assert source.gate_snapshot()["restarts_seen"] == 1
    assert CombinedGate(lambda: (True, ""), lambda: source).check() == (False, reason)
    time.sleep(0.3)
    assert len(slm.calls) == k
    assert source.poll_status()
    assert source.check() == (True, "")

    # the source follows the new host
    source.begin_scan()
    assert mode_of(source.snap(3.0)) == MODE_CODE["snap"]


@needs_stream
def test_video_never_shows_run_frames(host):
    source = host.open_source()
    frames, stopped = [], threading.Event()
    source.start_video(frames.append, stopped.set)
    assert wait_until(lambda: len(frames) >= 3, timeout=5.0)
    assert source.video_running() and source.video_note() == ""

    host.take_camera_for_run(n_frames=3)
    assert stopped.wait(5.0)                     # the run took the camera: video ends
    assert not source.video_running()
    assert "took liveOD's Andor" in source.video_stop_reason
    # there were run frames (published by the worker once it pumps the triggers)
    assert wait_until(lambda: host.worker.slot.latest(sources=("run",)) is not None)

    n = len(frames)
    stopped.clear()
    source.start_video(frames.append, stopped.set)   # started again during the run
    assert stopped.wait(5.0)
    assert len(frames) == n
    assert all(mode_of(f) in (MODE_CODE["live"], MODE_CODE["snap"]) for f in frames)
    host.end_run()


def live_requesters(host):
    return host.core.snapshot()["cameras"][ANDOR_ID]["live_requesters"]


def count_stop_live(host, monkeypatch):
    """The client_id of every STOP_LIVE the host receives, in a list."""
    sent = []
    real = host.core._v2_handlers["STOP_LIVE"]

    def h_stop_live(req):
        sent.append(req.header.get("client_id"))
        return real(req)
    monkeypatch.setitem(host.core._v2_handlers, "STOP_LIVE", h_stop_live)
    return sent


@needs_stream
def test_video_starts_an_idle_liveod_andor_and_gives_it_back(host):
    w = host.worker
    w.call("stop_live", 5.0)                     # liveOD has the Andor open, not streaming
    assert w.state == "idle" and live_requesters(host) == []
    source = host.open_source()
    frames, stopped = [], threading.Event()
    source.start_video(frames.append, stopped.set)
    assert wait_until(lambda: len(frames) >= 3, timeout=5.0)    # START_LIVE started it
    assert w.state == "streaming" and source.video_note() == ""
    mine = live_requesters(host)
    assert len(mine) == 1 and mine[0].startswith("v2:")
    assert all(mode_of(f) == MODE_CODE["live"] for f in frames)
    source.stop_video()                          # the last requester: the stream stops
    assert stopped.wait(5.0) and source.video_stop_reason == ""
    assert wait_until(lambda: w.state == "idle") and live_requesters(host) == []

    frames.clear()
    source.start_video(frames.append)
    assert wait_until(lambda: len(frames) >= 1, timeout=5.0)
    source.close()                               # close gives it back too
    assert wait_until(lambda: w.state == "idle") and w.is_open   # liveOD keeps the camera

    # liveOD's own live view asked for the stream: the spot finder never ends it
    host.core.request_live(ANDOR_ID, "liveod").result(5)
    source = host.open_source()
    frames.clear()
    source.start_video(frames.append)
    assert wait_until(lambda: len(frames) >= 2, timeout=5.0)
    assert "liveod" in live_requesters(host) and len(live_requesters(host)) == 2
    source.stop_video()
    time.sleep(0.3)
    assert w.state == "streaming" and live_requesters(host) == ["liveod"]
    host.core.release_live(ANDOR_ID, "liveod").result(5)
    assert wait_until(lambda: w.state == "idle")


@needs_stream
def test_video_refused_by_the_host_stops_at_once_and_says_why(host, monkeypatch):
    w = host.worker
    sent = count_stop_live(host, monkeypatch)
    source = host.open_source()
    frames, stopped = [], threading.Event()

    # a run holds liveOD's Andor: no live stream
    host.take_camera_for_run(trigger=False)
    source.start_video(frames.append, stopped.set)
    assert stopped.wait(5.0) and not source.video_running() and frames == []
    reason = source.video_stop_reason
    assert reason.startswith("video not started: run 80713 holds liveOD's Andor"), reason
    assert "starts no live stream during a run" in reason
    note = source.video_note()
    assert note.startswith("No live video: run 80713") and "when the run is over" in note
    assert w.locked_by == "RUN" and w.state == "acquiring"   # the run's acquisition, untouched
    source.stop_video()
    host.end_run()

    # a closed camera: never opened for the spot finder
    w.call("close", 5.0)
    stopped.clear()
    source.start_video(frames.append, stopped.set)
    assert stopped.wait(5.0) and frames == []
    assert "not open" in source.video_stop_reason
    assert "open it in liveOD, then start the video again" in source.video_note()
    assert not w.is_open

    # the host's write policy says no (another PC is view only)
    w.call("open", 5.0)
    host.core.write_policy = lambda addr, cid, keys: (False, "view only: not this PC")
    stopped.clear()
    source.start_video(frames.append, stopped.set)
    assert stopped.wait(5.0) and frames == []
    assert "refused the live stream: view only: not this PC" in source.video_stop_reason
    assert w.state == "idle"
    assert sent == []                            # nothing to give back after a refusal

    # allowed again: the note goes, and the one request made is given back once
    host.core.write_policy = None
    source.start_video(frames.append, stopped.set)
    assert wait_until(lambda: len(frames) >= 1, timeout=5.0)
    assert source.video_note() == ""
    source.stop_video()
    assert len(sent) == 1
    assert wait_until(lambda: w.state == "idle")


@needs_stream
def test_a_stopping_host_ends_video_and_snap_like_a_restart(host, monkeypatch):
    import frame_source
    from frame_source import ServerStopping, Preempted
    # what CameraServerCore answers every parked request while it stops
    stopping = {"ok": False, "code": "shutdown", "error": "server stopping"}
    handlers = host.core._v2_handlers
    real_wait = handlers["WAIT_FRAME"]
    source = host.open_source()
    frames, stopped = [], threading.Event()
    source.start_video(frames.append, stopped.set)
    assert wait_until(lambda: len(frames) >= 2, timeout=5.0)
    monkeypatch.setitem(handlers, "WAIT_FRAME", lambda req: dict(stopping))
    assert stopped.wait(5.0) and not source.video_running()
    assert "liveOD's camera host is shutting down" in source.video_stop_reason
    ok, why = source.check()
    assert not ok and "shutting down" in why     # the gate holds, as after a restart
    monkeypatch.setitem(handlers, "WAIT_FRAME", real_wait)

    source.begin_scan()                          # a newer status: the gate opens
    assert source.check() == (True, "")
    monkeypatch.setitem(handlers, "SNAP", lambda req: dict(stopping))
    with pytest.raises(ServerStopping) as err:
        source.snap(2.0)
    assert isinstance(err.value, Preempted) and err.value.reason == "shutdown"
    assert not source.check()[0]
    assert scan_group.preempt_text(err.value)[0] == "camera host shutting down"
    assert frame_source._preempt_what(err.value) == "liveOD's camera host is shutting down"


@needs_stream
def test_apply_reports_run_locked(host):
    source = host.open_source()
    ps = source.panel_settings()
    assert ps["exposure_s"] == pytest.approx(0.02) and ps["gain"] == 1
    assert ps["shutter_open"] is True

    ok, msg = source.apply(0.03, 5)
    assert ok and msg.startswith("Applied:") and "exposure=0.0300s" in msg and "gain=5" in msg
    assert host.backend.settings["gain"] == 5
    assert host.backend.settings["exposure_time"] == pytest.approx(0.03)
    ok, msg = source.apply(20.0, 5)             # past the camera's range: clamped, and said so
    assert not ok and "exposure NOT SET" in msg and "(clamped)" in msg

    host.take_camera_for_run(trigger=False)
    n_applied = len(host.backend.applied)
    ok, msg = source.apply(0.05, 3)
    assert not ok and "run 80713 holds liveOD's Andor" in msg
    assert "no settings during a run" in msg
    ok, msg = source.set_shutter(False)
    assert not ok and "run 80713" in msg
    assert len(host.backend.applied) == n_applied        # nothing reached the camera

    host.end_run()
    ok, msg = source.set_shutter(False)
    assert ok and host.backend.settings["shutter"] == "closed", msg


class FakeDirectory:
    """CameraDirectory.list() stand-in: ``entries``, once ``release`` is set."""

    def __init__(self, entries=(), release=None, error=None):
        self.entries = list(entries)
        self.release = release
        self.error = error
        self.calls = 0

    def list(self):
        self.calls += 1
        if self.release is not None:
            assert self.release.wait(10)
        if self.error is not None:
            raise self.error
        return list(self.entries)

    def close(self):
        pass


def entry(server_id, state="streaming", camera_id=ANDOR_ID, holder=None):
    cat, _, serial = camera_id.partition(":")
    return CameraEntry(camera_id=camera_id, category=cat, serial=serial, name="andor",
                       model="FakeEMCCD", server_id=server_id, host="127.0.0.1", port=1,
                       state=state, holder=holder, protocol="v2", server_ids=(server_id,))


@needs_stream
def test_find_liveod_andor_takes_only_a_liveod_host():
    from frame_source import find_liveod_andor
    e, why = find_liveod_andor(FakeDirectory([entry("camera_server:kong")]))
    assert e is None and why == "liveOD does not serve the Andor (camera host off)"
    e, why = find_liveod_andor(FakeDirectory(
        [entry(HOST_ID, camera_id="basler_usb:40320384"), entry(HOST_ID)]))
    assert e.camera_id == ANDOR_ID and why == ""
    e, why = find_liveod_andor(FakeDirectory(
        [entry(HOST_ID, state="reserved", holder={"label": "tweezer balance"})]))
    assert e is None and "reserved" in why and "tweezer balance" in why


@needs_stream
def test_source_selection_falls_back_to_local_with_banner(app, slm_host, monkeypatch):
    import SLM_andor_main_gui as main_gui
    from frame_source import LocalAndorSource
    opened = []

    def fake_andor(**kw):
        opened.append(kw)
        return FakeCamera(SLMPattern())

    monkeypatch.setattr(main_gui, "AndorEMCCD", fake_andor)     # never the real SDK

    # auto, and the directory finds nothing: the local camera, with the banner
    release = threading.Event()
    directory = FakeDirectory(release=release)
    w = build_window(slm_host, monkeypatch, None, directory=directory)
    try:
        assert process_until(app, lambda: directory.calls == 1)
        app.processEvents()                     # the GUI runs while discovery waits
        assert w.camera_pill.state == "loading" and not opened
        assert not w._camera_connected() and not w.scan_btn.isEnabled()
        release.set()
        assert process_until(app, lambda: w._camera_connected())
        assert isinstance(w.source, LocalAndorSource) and len(opened) == 1
        assert not w.source_banner.isHidden()
        text = w.source_banner.text()
        assert "liveOD does not serve the Andor (camera host off)" in text
        assert "using the camera directly; release it in liveOD first" in text
        assert w.camera_pill.state == "open"
    finally:
        close_window(w)

    # a lookup that fails falls back the same way, and says why
    opened.clear()
    w = build_window(slm_host, monkeypatch, None,
                     directory=FakeDirectory(error=OSError("no route to the lab network")))
    try:
        assert process_until(app, lambda: w._camera_connected())
        assert len(opened) == 1
        assert "Looking for liveOD's camera host failed" in w.source_banner.text()
        assert "no route to the lab network" in w.source_banner.text()
    finally:
        close_window(w)

    # --stream: nothing served means no camera at all; the andor button looks again
    opened.clear()
    directory = FakeDirectory()
    w = build_window(slm_host, monkeypatch, None, directory=directory, source_mode="stream")
    try:
        assert process_until(app, lambda: w.camera_pill.state == "failed")
        assert "--stream was given" in w.source_banner.text()
        w.connect_camera()
        app.processEvents()
        assert not opened and not w._camera_connected() and not w.scan_btn.isEnabled()
        w.camera_pill.click()
        assert process_until(app, lambda: directory.calls == 2
                             and w.camera_pill.state == "failed")
        assert not opened
    finally:
        close_window(w)

    # --direct: liveOD's camera host is not asked
    directory = FakeDirectory()
    w = build_window(slm_host, monkeypatch, None, directory=directory, source_mode="direct")
    try:
        assert process_until(app, lambda: w._camera_connected())
        assert directory.calls == 0 and len(opened) == 1
        assert "--direct" in w.source_banner.text()
    finally:
        close_window(w)

    assert main_gui.parse_source_mode([]) == "auto"
    assert main_gui.parse_source_mode(["--direct"]) == "direct"
    assert main_gui.parse_source_mode(["--stream", "-platform", "offscreen"]) == "stream"
    with pytest.raises(SystemExit):
        main_gui.parse_source_mode(["--direct", "--stream"])


@needs_stream
def test_source_selection_attaches_to_liveod_andor_when_served(app, slm_host, monkeypatch,
                                                               host):
    import SLM_andor_main_gui as main_gui
    from frame_source import StreamSource

    def no_camera(**kw):
        raise AssertionError("the window opened the Andor directly")

    monkeypatch.setattr(main_gui, "AndorEMCCD", no_camera)
    n_applied = len(host.backend.applied)
    w = build_window(slm_host, monkeypatch, None, directory=host.directory())
    try:
        assert process_until(app, lambda: w._camera_connected())
        assert isinstance(w.source, StreamSource)
        assert "Andor through liveOD" in w.source_banner.text()
        assert HOST_ID in w.source_banner.text()
        # liveOD's settings are shown, not overwritten
        assert w.exposure_sb.value() == pytest.approx(0.02) and w.gain_sb.value() == 1
        assert len(host.backend.applied) == n_applied
        assert w.camera_pill.state == "open"
        assert process_until(app, lambda: w._gate_open)

        # Apply goes to liveOD's live settings (off the GUI thread) and reports the readback
        w.exposure_sb.setValue(0.03)
        w.gain_sb.setValue(4)
        w.apply_cam_btn.click()
        assert process_until(app, lambda: w.cam_param_status.text().startswith("Applied:"))
        assert host.backend.settings["gain"] == 4
        assert host.backend.settings["exposure_time"] == pytest.approx(0.03)

        frames = []
        w._frame_sig.connect(frames.append)
        w.video_btn.click()
        assert process_until(app, lambda: len(frames) >= 3)
        assert w.camera_pill.state == "grabbing"

        # a run takes liveOD's Andor: the video stops, the gate closes, no SLM write
        n_up = len(slm_host.uploads)
        host.take_camera_for_run()
        assert process_until(app, lambda: not w.video_btn.isChecked())
        assert process_until(app, lambda: not w._gate_open
                             and "80713" in w.run_banner.text())
        assert "holds liveOD's Andor" in w.run_banner.text()
        w.slm.set_center(10, 10)
        time.sleep(0.2)
        app.processEvents()
        assert len(slm_host.uploads) == n_up
        # the camera takes no settings during the run: the shutter button goes back
        was_open = w.shutter_btn.isChecked()
        w.shutter_btn.click()
        assert process_until(app, lambda: "holds liveOD's Andor" in w.cam_param_status.text())
        assert process_until(app, lambda: w.shutter_btn.isChecked() == was_open)

        # the run ends: the gate opens, the SLM state is unknown, nothing is sent by itself
        host.end_run()
        assert process_until(app, lambda: w._gate_open)
        assert "took liveOD's Andor" in w.slm_sync_label.text()
        time.sleep(0.2)
        app.processEvents()
        assert len(slm_host.uploads) == n_up
    finally:
        close_window(w)
    assert host.worker.is_open                  # detached; liveOD keeps its camera


@needs_stream
def test_stream_source_satisfies_protocol():
    import inspect
    import frame_source
    from beacon.camera import stream as beacon_stream
    members = [n for n, v in vars(frame_source.FrameSource).items()
               if callable(v) and not n.startswith("_")]
    assert set(members) == {"is_open", "open", "close", "frame_period", "start_video",
                            "stop_video", "video_running", "apply", "set_shutter",
                            "begin_scan", "snap", "end_scan", "run_state"}
    for name in members:
        want = list(inspect.signature(getattr(frame_source.FrameSource, name)).parameters)
        for cls in (frame_source.StreamSource, frame_source.LocalAndorSource):
            got = list(inspect.signature(getattr(cls, name)).parameters)
            assert got == want, (cls.__name__, name, got, want)

    # one Preempted: what beacon's stream raises is what run_scan catches
    assert frame_source.Preempted is beacon_stream.Preempted
    assert frame_source.ServerRestarted is beacon_stream.ServerRestarted
    assert frame_source.ServerStopping is beacon_stream.ServerStopping
    assert scan_group.Preempted is frame_source.Preempted

    # not attached: no camera, no run, no opinion on the gate, nothing running
    s = frame_source.StreamSource("andor", directory=FakeDirectory())
    assert not s.is_open() and not s.video_running()
    assert s.run_state() == frame_source.RunState()
    assert s.check() == (True, "") and s.gate_snapshot()["state"] == "detached"
    s.stop_video()
    s.end_scan()
    s.close()
    with pytest.raises(RuntimeError, match="not attached"):
        s.snap(1.0)
    ok, msg = s.apply(0.01, 1)
    assert not ok and "not attached" in msg

    # discovery stays within about 3 s, and only liveOD's hosts count
    assert frame_source.DISCOVERY_COLLECT_S + 2 * frame_source.DISCOVERY_REQUEST_S <= 3.0
    assert frame_source.is_liveod_server("camera_server:kong:liveod")
    assert not frame_source.is_liveod_server("camera_server:kong")
    assert not frame_source.is_liveod_server("basler_server:kong")
