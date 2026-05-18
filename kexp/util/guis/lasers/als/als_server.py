from waxx.util.guis.als.als_server import main as run_als_server

from kexp.config.ip import ALS_COM


def main() -> None:
    """Launch the standalone ALS hardware server."""
    run_als_server(serial_port=ALS_COM)


if __name__ == "__main__":
    main()
