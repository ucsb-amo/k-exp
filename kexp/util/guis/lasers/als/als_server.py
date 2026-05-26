import os

from waxx.util.guis.als.als_server import main as run_als_server

from kexp.config.ip import ALS_COM, DATA_DIR

_LOG_PATH = os.path.join(DATA_DIR, "_logs", "als_server.log") if DATA_DIR else None


def main() -> None:
    """Launch the standalone ALS hardware server."""
    run_als_server(serial_port=ALS_COM, log_path=_LOG_PATH)


if __name__ == "__main__":
    main()
