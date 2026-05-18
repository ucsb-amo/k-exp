from waxx.util.guis.precilaser.precilaser_server import main as run_precilaser_server

from kexp.config.ip import (
    PRECILASER_COM,
)


def main() -> None:
    """Launch the standalone Precilaser hardware server."""
    run_precilaser_server(
        serial_port=PRECILASER_COM,
    )


if __name__ == "__main__":
    main()
