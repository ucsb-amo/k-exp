from waxx.util.guis.als.als_server import main as run_als_server

from kexp.config.ip import ALS_SERVER_IP, ALS_SERVER_PORT, ALS_COM


def main() -> None:
    """Launch the standalone ALS hardware server."""
    run_als_server(host=ALS_SERVER_IP, port=ALS_SERVER_PORT, serial_port=ALS_COM)


if __name__ == "__main__":
    main()
