"""The SLM spot finder, offline: a fake camera, a fake stage, and the real SLM
run_server connection handling on localhost with the Meadowlark calls stubbed.
No hardware, no lab network.

What is checked is what the scan exists to get right: every frame is filed
under the SLM position that was up for the whole of its exposure. The fakes
model the timing that matters -- an acquisition's first exposure starts after
start_acquisition(), the SLM changes pattern some time after a command -- and
nothing else, so these tests say the sequencing is right, not that the Andor
or the Meadowlark behave like the fakes.

SPOT_FINDER_DIR, if set, is the spot finder package to test instead of the one
in k-exp (a copy being worked on outside the guarded tree). Tests of the run
gate and the FrameSource seam skip on a package that predates them.
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


@pytest.fixture
def gui(app, slm_host, monkeypatch):
    import stage_group
    import SLM_andor_main_gui as main_gui
    FakeStage.calls = []
    monkeypatch.setattr(stage_group, "APDStageClient", FakeStage)
    monkeypatch.setattr(main_gui.FinalScanPreviewDialog, "exec", lambda self: 0)
    # never the lab SLM PC, not even for the startup reachability probe
    monkeypatch.setattr(main_gui, "SLMController", lambda canvas_res, **kw: SLMController(
        canvas_res=canvas_res, server_ip="127.0.0.1", server_port=slm_host.port,
        **{k: v for k, v in kw.items() if k == "write_gate"}))
    pattern = SLMPattern()
    camera = FakeCamera(pattern)
    kwargs, gate, liveod = {}, None, None
    if HAS_SEAM:
        # never the lab liveOD either: the run state is a dict the test sets
        from run_gate import RunGate
        liveod = {"ok": True, "run_in_progress": False, "run_id": 80712}
        gate = RunGate(status_fn=lambda: dict(liveod), poll_period_s=0.02)
        kwargs["run_gate"] = gate
    w = main_gui.UnifiedControlGUI(camera, connect_camera_on_start=False, **kwargs)
    w._test_pattern = pattern
    w._test_liveod = liveod
    if HAS_SEAM:
        assert process_until(app, lambda: w._gate_open)
    yield w
    w.close()
    if gate is not None:
        gate.stop()


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
