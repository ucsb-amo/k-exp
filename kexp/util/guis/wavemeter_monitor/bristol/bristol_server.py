"""Entry point: Bristol wavemeter server, using kexp IP configuration."""
from waxx.util.guis.bristol.bristol_wavemeter_server_gui import main as run_server_gui
from kexp.config.ip import BRISTOL_WAVEMETER_IP


def main() -> None:
    run_server_gui(wavemeter_host=BRISTOL_WAVEMETER_IP)


if __name__ == "__main__":
    main()
