"""A cold queue launch with WAXX_CLAIM_OVERLAP on: the claim beside the compile.

The harness of test_claim_split_compiles (a real Base experiment, every network
client stubbed, every claim step recorded, no socket may leave this machine),
with ``WAXX_LAUNCHER=kq`` and ``WAXX_CLAIM_OVERLAP=1`` set as the run queue's
launcher would hand them over.

* prepare() claims nothing: the stage's throw starts on its own thread in
  Base.__init__, the claim is handed to waxx claim_overlap;
* run() (the real waxx Core, its two senders stubbed: nothing goes to the core
  device) starts the claim on a thread, compiles the kernel, waits for the
  claim, and only then "uploads". The claim's steps are the cold ones in the
  cold order, they happen while the compile runs, and every attribute the
  kernel embeds has the same value after the claim as before it;
* a compile that raises stops the claim before the liveOD start: no run id;
* with the overlap off (the default), or a host run(), the claim is in
  finish_prepare as it always was.

Each real compile takes ~10 s. Skipped when %db% / %code% are not set.
"""
import os
import time

import pytest

from test_claim_split_compiles import (  # noqa: F401 (fixture)
    EXPT, FEEDBACK_EXPT, NO_FINISH_PREPARE_EXPT, _assert_claim_order, _build, _claim_events,
    _cleanup, _compile, _kernel_view, _stamped_trust, no_outbound_sockets)

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

HOST_RUN_EXPT = '''
from artiq.experiment import *
from kexp import Base, cameras
import numpy as np

class HostRunClaims(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=True, camera_select=cameras.apd,
                      save_data=False, diagnostic_images=False)
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        delay(self.p.t_tof)

    def run(self):
        pass
'''

T_STAGE = 1.5       # the fake stage's throw (s): still going when prepare() returns


@pytest.fixture
def overlap(monkeypatch):
    """The environment of a cold queue launch with the overlap on, and a
    stage whose throw takes T_STAGE s."""
    from waxx.util.device_state import claim_overlap as co
    monkeypatch.setenv("WAXX_LAUNCHER", "kq")
    monkeypatch.setenv(co.ENV, "1")
    co._reset_for_tests()
    real_background = co.background

    def slow_background(name, fn, daemon=True):
        def slow():
            time.sleep(T_STAGE)
            return fn()
        return real_background(name, slow, daemon)

    monkeypatch.setattr(co, "background", slow_background)
    yield co
    co._reset_for_tests()


def _stub_senders(monkeypatch, b):
    """The Core's two calls that talk to the core device, recorded instead;
    the real compile, recorded and its result kept."""
    core = b.exp.core
    compiled = []
    real_compile = core.compile

    def compile(*args, **kwargs):
        b.events.append(("compile",))
        out = real_compile(*args, **kwargs)
        b.events.append(("compile_end",))
        compiled.append(out)
        return out

    monkeypatch.setattr(core, "compile", compile, raising=False)
    monkeypatch.setattr(core, "compile_and_upload_subkernels",
                        lambda *a, **k: b.events.append(("upload",)), raising=False)
    monkeypatch.setattr(core, "_run_compiled",
                        lambda *a, **k: b.events.append(("run_compiled",)), raising=False)
    return compiled


def _slow_claim_steps(monkeypatch, b):
    """Spread the claim over the compile, as the real steps' waits do."""
    from waxx.control.cameras import camera_stream_client as csc
    fast_resolve = csc.CameraStreamClient._resolve_and_connect

    def resolve(self, directory):
        time.sleep(0.2)
        return fast_resolve(self, directory)

    monkeypatch.setattr(csc.CameraStreamClient, "_resolve_and_connect", resolve)
    fast_init = b.liveod.init_run

    def init_run(payload):
        time.sleep(0.5)
        return fast_init(payload)

    b.liveod.init_run = init_run


def test_overlap_claims_beside_the_compile_in_order_and_changes_no_kernel_value(
        monkeypatch, tmp_path, no_outbound_sockets, overlap):
    co = overlap
    b = _build(monkeypatch, tmp_path, warm=False)
    try:
        ev = b.events
        # prepare(): no claim, nothing on liveOD, no run id; the stage's throw
        # is on its thread (not landed yet)
        assert not any(e[0] == "claim" for e in ev)
        assert [e for e in _claim_events(ev) if e[0] != "pdxc"] == []
        assert co.claim_pending() and co.active()
        assert b.exp._claimed is False and b.exp._run_started is False
        assert b.exp.run_info.run_id == 0
        assert b.exp._apd_stage_task is not None
        assert b.state.exists()                          # cold: the reconcile ran

        # what the kernel embeds, before the claim (a compile of its own)
        before_map = _compile(b)[0]
        before = _kernel_view(before_map)
        assert before
        n_before = len(ev)

        _slow_claim_steps(monkeypatch, b)
        compiled = _stub_senders(monkeypatch, b)
        b.exp.run()                                      # the real Core: claim beside compile

        run_ev = ev[n_before:]
        names = [e[0] for e in run_ev]
        assert names.count("claim") == 1 and names.count("compile") == 1
        i_c0, i_c1 = names.index("compile"), names.index("compile_end")
        i_up, i_run = names.index("upload"), names.index("run_compiled")
        # the claim starts while the kernel compiles ...
        assert names.index("claim") < i_c1 and i_c0 < i_c1, names
        # ... and nothing is sent before its last step
        last_claim_step = max(i for i, n in enumerate(names)
                              if n in ("announce", "stamp", "liveod_init", "cam_connect"))
        assert i_c1 < i_up < i_run and last_claim_step < i_up, names
        assert len(compiled) == 1

        # the cold claim, in the cold order
        _assert_claim_order(ev)
        assert [e for e in ev if e[0] == "pdxc"] == [("pdxc", True), ("pdxc", True)]
        assert ("liveod_init",) in ev
        assert ("liveod_reserve",) not in ev and not any(e[0] == "liveod_start" for e in ev)
        assert b.exp.run_info.run_id == 4242
        assert b.exp._claimed and b.exp._run_started
        assert all(s.live for s in b.exp.diag.streams().values() if hasattr(s, "connect"))
        shapes = b.liveod.payloads["init"]["datavault_shapes"]
        for s in b.exp.diag.streams().values():
            if hasattr(s, "connect"):
                assert shapes[s.keys[0]]["shape"][1:] == s._frame_shape != (1,)
        assert _stamped_trust(b.exp) == {"trusted": True,
                                         "reason": "the previous run's end state"}
        assert "slm_at_start" in b.exp._extra_file_texts

        # the claim set nothing the kernel reads
        after = _kernel_view(before_map)
        changed = sorted(k for k in before if after.get(k) != before[k])
        assert changed == [], f"the claim changed kernel-embedded attributes: {changed}"

        rep = co.report()
        assert set(rep) == {"compile_s", "claim_s", "waited_after_compile_s"}
        assert rep["claim_s"] >= 0.5 and rep["compile_s"] > 0
        assert not co.active()

        n = len(ev)
        b.exp.claim()                                    # idempotent
        assert len(_claim_events(ev)) == len(_claim_events(ev[:n]))
    finally:
        _cleanup(b)


def test_overlap_a_compile_that_fails_takes_no_run_id(monkeypatch, tmp_path,
                                                      no_outbound_sockets, overlap):
    co = overlap
    import sys
    # a throw long enough to be still going when run() is called
    monkeypatch.setattr(sys.modules[__name__], "T_STAGE", 4.0)
    b = _build(monkeypatch, tmp_path, warm=False)
    try:
        core = b.exp.core

        def compile(*args, **kwargs):
            raise RuntimeError("compile test: the kernel does not compile")

        monkeypatch.setattr(core, "compile", compile, raising=False)
        monkeypatch.setattr(core, "compile_and_upload_subkernels",
                            lambda *a, **k: b.events.append(("upload",)), raising=False)
        monkeypatch.setattr(core, "_run_compiled",
                            lambda *a, **k: b.events.append(("run_compiled",)), raising=False)
        with pytest.raises(RuntimeError, match="does not compile"):
            b.exp.run()
        ev = b.events
        # the claim was waiting for the stage: it stopped there
        assert ("liveod_init",) not in ev and not any(e[0] == "announce" for e in ev)
        assert ("upload",) not in ev and ("run_compiled",) not in ev
        assert b.exp.run_info.run_id == 0 and b.exp._run_started is False
        assert not co.claim_pending()
        time.sleep(T_STAGE + 0.3)                        # let the fake throw end
    finally:
        _cleanup(b)


def test_overlap_off_by_default_claims_in_finish_prepare(monkeypatch, tmp_path,
                                                         no_outbound_sockets):
    from waxx.util.device_state import claim_overlap as co
    monkeypatch.setenv("WAXX_LAUNCHER", "kq")
    monkeypatch.delenv(co.ENV, raising=False)
    co._reset_for_tests()
    assert co.DEFAULT_ON is False
    b = _build(monkeypatch, tmp_path, warm=False)
    try:
        ev = b.events
        assert [e for e in ev if e[0] == "claim"] == [("claim",)]
        assert ("liveod_init",) in ev and b.exp.run_info.run_id == 4242
        assert b.exp._apd_stage_task is None
        assert not co.active()
        _assert_claim_order(ev)
    finally:
        _cleanup(b)


def test_overlap_a_host_run_claims_in_finish_prepare(monkeypatch, tmp_path,
                                                     no_outbound_sockets, overlap):
    """run() is not a kernel: host code could run before any compile, so the
    stage moves in Base.__init__ and the claim is in finish_prepare, as ever."""
    co = overlap
    b = _build(monkeypatch, tmp_path, warm=False, source=HOST_RUN_EXPT)
    try:
        ev = b.events
        assert [e for e in ev if e[0] == "claim"] == [("claim",)]
        assert ev.index(("pdxc", True)) < ev.index(("claim",))
        assert b.exp._apd_stage_task is None and b.exp.run_info.run_id == 4242
        assert not co.active()
    finally:
        _cleanup(b)


def test_overlap_a_stage_tool_without_finish_prepare_moves_the_stage_at_once(
        monkeypatch, tmp_path, no_outbound_sockets, overlap):
    co = overlap
    b = _build(monkeypatch, tmp_path, warm=False, source=NO_FINISH_PREPARE_EXPT)
    try:
        assert ("pdxc", False) in b.events               # host run(): moved in __init__
        assert not any(e[0] == "claim" for e in b.events)
        assert not co.active()
    finally:
        _cleanup(b)


def test_overlap_feedback_run_and_the_claim_changes_no_kernel_value(
        monkeypatch, tmp_path, no_outbound_sockets, overlap):
    """The feedback family (the heaviest kernel, its own finish_prepare)."""
    co = overlap
    b = _build(monkeypatch, tmp_path, warm=False, source=FEEDBACK_EXPT)
    try:
        assert not any(e[0] == "claim" for e in b.events) and co.claim_pending()
        before_map = _compile(b)[0]
        before = _kernel_view(before_map)
        n_before = len(b.events)
        _slow_claim_steps(monkeypatch, b)
        _stub_senders(monkeypatch, b)
        b.exp.run()
        names = [e[0] for e in b.events[n_before:]]
        assert names.count("claim") == 1
        assert names.index("claim") < names.index("compile_end") < names.index("upload")
        assert ("liveod_init",) in b.events and b.exp.run_info.run_id == 4242
        after = _kernel_view(before_map)
        changed = sorted(k for k in before if after.get(k) != before[k])
        assert changed == [], f"the claim changed kernel-embedded attributes: {changed}"
    finally:
        _cleanup(b)
