from waxx.util.guis.precilaser.precilaser_server import main as run_precilaser_server

from kexp.config.ip import (
    PRECILASER_COM,
    PRECILASER_SERVER_IP,
    PRECILASER_SERVER_PORT,
)


def main() -> None:
    """Launch the standalone Precilaser hardware server."""
    run_precilaser_server(
        host=PRECILASER_SERVER_IP,
        port=PRECILASER_SERVER_PORT,
        serial_port=PRECILASER_COM,
    )


if __name__ == "__main__":
    main()
