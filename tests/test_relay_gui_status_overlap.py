"""Ethernet relay GUI (kexp.util.guis.ethernet_relay.ethernet_relay_gui): the
5 s status tick must never start a second status read while one is running,
and a running worker thread must never lose its last reference (that aborts
the process with "QThread: Destroyed while thread is still running").

The relay is a fake whose status read blocks until the test releases it;
nothing goes on the network.  Offscreen Qt."""
import gc
import os
import threading
import time

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class BlockingRelay:
    """Stands in for EthernetRelay. read_relay_status blocks until
    ``release`` is set; operations record themselves and return."""

    def __init__(self, status=(False, True, False, False)):
        self.release = threading.Event()
        self.status = list(status)
        self.fail = None
        self.read_calls = []
        self.ops = []
        self._active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def _enter(self):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)

    def _leave(self):
        with self._lock:
            self._active -= 1

    def read_relay_status(self, **kwargs):
        self._enter()
        try:
            self.read_calls.append(kwargs)
            self.release.wait(10)
            if self.fail is not None:
                raise self.fail
            return list(self.status)
        finally:
            self._leave()

    def source_on(self):
        self._enter()
        try:
            self.ops.append("source_on")
        finally:
            self._leave()

    def source_off(self):
        self._enter()
        try:
            self.ops.append("source_off")
        finally:
            self._leave()


def _spin(cond, timeout=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    QApplication.processEvents()
    return cond()


@pytest.fixture
def gui(qapp):
    from kexp.util.guis.ethernet_relay.ethernet_relay_gui import EthernetRelayGUI
    relay = BlockingRelay()
    g = EthernetRelayGUI(relay=relay)
    g.status_timer.stop()          # the test drives the ticks itself
    yield g, relay
    relay.release.set()
    for w in list(g._workers):
        w.wait(5000)
    QApplication.processEvents()
    g.deleteLater()
    QApplication.processEvents()


def test_a_slow_status_read_blocks_further_ticks(gui):
    g, relay = gui
    assert _spin(lambda: len(relay.read_calls) == 1)
    first = g.status_worker
    for _ in range(5):              # five more 5 s ticks while the read hangs
        g.update_status()
    gc.collect()
    QApplication.processEvents()
    assert len(relay.read_calls) == 1
    assert g.status_worker is first and first.isRunning()
    assert first in g._workers

    relay.release.set()
    assert first.wait(5000)
    assert _spin(lambda: g.status_indicator.text() == "OFF")
    assert g.magnet_status_btn.text() == "ON"

    g.update_status()                # the next tick starts a new read
    assert _spin(lambda: len(relay.read_calls) == 2)


def test_the_status_probe_is_bounded(gui):
    g, relay = gui
    assert _spin(lambda: len(relay.read_calls) == 1)
    assert relay.read_calls[0] == {"retries": 0, "timeout": 3.0}


def test_an_operation_waits_for_the_status_read(gui):
    """Status read and operation never use the shared relay at once, and
    the pre-operation read is not shown afterwards."""
    g, relay = gui
    assert _spin(lambda: len(relay.read_calls) == 1)
    status_worker = g.status_worker
    g.toggle_source()                       # source_status False -> source_on
    op_worker = g.worker
    time.sleep(0.1)
    assert relay.ops == []                  # waiting for the status read
    relay.release.set()
    assert op_worker.wait(5000) and status_worker.wait(5000)
    assert relay.ops == ["source_on"]
    assert relay.max_active == 1
    assert _spin(lambda: not g.operation_in_progress)


def test_a_status_error_leaves_an_operation_alone(gui):
    g, relay = gui
    assert _spin(lambda: len(relay.read_calls) == 1)
    relay.fail = OSError("unreachable")
    g.operation_in_progress = True          # an operation started meanwhile
    g.set_buttons_enabled(False)
    relay.release.set()
    assert g.status_worker.wait(5000)
    _spin(lambda: False, timeout=0.2)
    assert g.operation_in_progress
    assert not g.toggle_btn.isEnabled()


def test_error_indicator_clears_when_state_is_unchanged(gui):
    g, relay = gui
    relay.release.set()
    assert _spin(lambda: g.status_indicator.text() == "OFF")
    assert _spin(lambda: not g.status_read_in_flight())
    relay.fail = OSError("unreachable")
    g.update_status()
    assert _spin(lambda: g.status_indicator.text() == "ERROR")
    assert _spin(lambda: not g.status_read_in_flight())
    relay.fail = None
    g.update_status()                       # same state as before the error
    assert _spin(lambda: g.status_indicator.text() == "OFF")
