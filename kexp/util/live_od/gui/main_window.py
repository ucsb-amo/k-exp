"""Launcher for the K machine's liveOD acquisition window.

    python -m kexp.util.live_od.gui.main_window          (or _bat/live_od.bat)

The window itself is waxx.util.live_od.gui.main_window and is lab-independent;
this file gives it kexp's configuration (kexp/config/live_od.py): where data goes,
which cameras exist, the default ROIs, the per-shot cross-section rule.

`LiveODWindow` and the rest of that module's names are importable from here, as
they always were.
"""
import waxx.util.live_od.gui.main_window as _impl

globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})


def main():
    from kexp.config.live_od import make_live_od_config
    _impl.main(make_live_od_config())


if __name__ == '__main__':
    main()
