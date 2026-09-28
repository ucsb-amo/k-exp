"""The Device Control GUI's SLM pill, kexp side: the spot finder launcher
(kexp.util.guis.device_state_gui.slm_tools) and its hand-over to the GUI.

Popen is a fake: nothing is started.
"""
import sys
import types

import pytest

from kexp.util.guis.device_state_gui import slm_tools


def test_spot_finder_is_where_the_launcher_looks():
    assert (slm_tools.SPOT_FINDER_DIR / slm_tools.SPOT_FINDER_SCRIPT).is_file()
    assert (slm_tools.SPOT_FINDER_DIR / "spot_finder.bat").is_file()


def test_command_quotes_for_cmd_and_pauses():
    cmd = slm_tools.spot_finder_command(python=r"C:\a b\python.exe")
    script = slm_tools.SPOT_FINDER_DIR / slm_tools.SPOT_FINDER_SCRIPT
    # cmd /c strips the outer pair, leaving: "python" "script" & pause
    assert cmd == f'cmd.exe /c ""C:\\a b\\python.exe" "{script}" & pause"'


def test_console_python_is_not_pythonw(monkeypatch, tmp_path):
    (tmp_path / "python.exe").write_text("")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    assert slm_tools._console_python() == str(tmp_path / "python.exe")


def test_launch_starts_it_detached_in_its_folder():
    calls = []

    def popen(cmd, **kw):
        calls.append((cmd, kw))
        return types.SimpleNamespace(pid=4242)

    what = slm_tools.launch_spot_finder(popen=popen)
    assert what.startswith("console pid 4242 on ")
    cmd, kw = calls[0]
    assert slm_tools.SPOT_FINDER_SCRIPT in cmd and cmd.startswith("cmd.exe /c ")
    assert kw["cwd"] == str(slm_tools.SPOT_FINDER_DIR)
    if sys.platform == "win32":
        import subprocess
        assert kw["creationflags"] & subprocess.CREATE_NEW_CONSOLE


def test_launch_refuses_a_missing_spot_finder(monkeypatch, tmp_path):
    monkeypatch.setattr(slm_tools, "SPOT_FINDER_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        slm_tools.launch_spot_finder(popen=lambda *a, **k: pytest.fail("started"))


def test_the_gui_gets_the_launcher_even_without_composite_definitions(monkeypatch):
    from kexp.util.guis.device_state_gui import monitor_panel
    kwargs = monitor_panel._composite_kwargs(None, None)
    assert kwargs.get("spot_finder_launcher") is slm_tools.launch_spot_finder
    # composite definitions that fail to load cost the tab, not the launcher
    import builtins
    real_import = builtins.__import__

    def failing(name, *a, **k):
        if name == "kexp.config.composite_devices":
            raise ImportError("broken on purpose")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", failing)
    kwargs = monitor_panel._composite_kwargs(None, None)
    assert kwargs == {"spot_finder_launcher": slm_tools.launch_spot_finder}
