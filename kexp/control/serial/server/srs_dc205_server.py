from waxx.control.misc.dc205 import DC205_Server

from kexp.config.ip import SRS_CONTROL_IP, SRS_DC205_SERVER_PORT, SRS_DC205_COM

def main():
    """Start the DC205 server."""
    server = DC205_Server(
        port=SRS_DC205_COM,
        server_ip=SRS_CONTROL_IP,
        server_port=SRS_DC205_SERVER_PORT)
    try:
        print("Starting DC205 Server...")
        server.start()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        server.stop()

if __name__ == '__main__':
    main()