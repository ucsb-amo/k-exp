"""The k-exp conftest keeps every test away from the live run queue's files
(~/.waxx/run_queue on kong) and from its live roots (%code%, the agents' log
folder): the queue's default folder and roots are the test's own temporary
folder, as in wax/waxx-src/tests/conftest.py."""
import os
from pathlib import Path


def test_the_run_queue_defaults_are_this_tests_temporary_folder(tmp_path):
    from waxx.util.device_state import queue_gate, run_queue
    live = os.path.normcase(str(Path.home() / ".waxx" / "run_queue"))
    assert os.path.normcase(run_queue.default_dir()) != live
    assert Path(run_queue.default_dir()).parent == tmp_path
    assert run_queue.default_roots() == queue_gate.queue_roots() == [str(tmp_path)]
