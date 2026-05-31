"""Entry point: Bristol wavemeter headless server, using kexp IP config.

This is the *headless* (no QApplication) server used when launched as a
subprocess by the dashboard supervisor.  The dashboard panel embeds the
client view (``BristolClientWindow``) which talks to this server over
ZMQ - so we don't want a second floating window.
"""
from waxx.util.guis.bristol.bristol_wavemeter_server import main as run_server
from kexp.config.ip import BRISTOL_WAVEMETER_IP


def main() -> None:
    run_server(wavemeter_host=BRISTOL_WAVEMETER_IP)


if __name__ == "__main__":
    main()
