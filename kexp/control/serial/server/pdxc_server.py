from waxx.control.misc.pdxc import PDXC_Server

from kexp.config.ip import PDXC_COM


def main() -> None:
    """Start the PDXC server on kong (192.168.1.76).

    Port is OS-assigned; clients discover it via UDP beacon.
    """
    server = PDXC_Server(com_port=PDXC_COM)
    try:
        print("Starting PDXC server...")
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.stop()


if __name__ == "__main__":
    main()
