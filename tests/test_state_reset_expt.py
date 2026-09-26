"""The Device Control GUI's Run MOT Observe runs kexp's reset experiment through
the monitor server (kexp.config.ip.RESET_STATE_EXPT_PATH): tools/mot_observe.py.
Its docstring names the button and is what the GUI shows before a reset, and
its end() is what reports the end state that marks the device state trusted."""
from pathlib import Path

import kexp
from kexp.config import ip
from waxx.util.device_state.state_reset import describe_expt
from waxx.util.guis.device_summary import reset_title

MOT_OBSERVE = Path(kexp.__file__).parent / "experiments" / "tools" / "mot_observe.py"


def test_the_reset_experiment_is_mot_observe():
    if ip.RESET_STATE_EXPT_PATH is not None:        # None when %code% is unset
        path = Path(ip.RESET_STATE_EXPT_PATH)
        assert (path.parent.name, path.name) == ("tools", "mot_observe.py")
    assert MOT_OBSERVE.is_file()


def test_mot_observe_says_what_it_leaves_on():
    about = describe_expt(MOT_OBSERVE)
    assert "INNER COIL ON" in about and "Run MOT Observe" in about
    assert reset_title({"expt": "mot_observe", "about": about}) == "MOT Observe"


def test_mot_observe_reports_its_end_state():
    source = MOT_OBSERVE.read_text(encoding="utf-8")
    assert "self.end(" in source and "restart_monitor=False" not in source
