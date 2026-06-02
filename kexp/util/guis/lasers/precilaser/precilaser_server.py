import os

from waxx.util.guis.precilaser.precilaser_server import main as run_precilaser_server

from kexp.config.ip import (
    DATA_DIR,
    PRECILASER_COM,
)

_LOG_PATH = os.path.join(DATA_DIR, "_logs", "precilaser_server.log") if DATA_DIR else None


def main() -> None:
    """Launch the standalone Precilaser hardware server."""
    run_precilaser_server(
        serial_port=PRECILASER_COM,
        log_path=_LOG_PATH,
    )


if __name__ == "__main__":
    main()
