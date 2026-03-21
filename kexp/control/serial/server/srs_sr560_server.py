from waxx.control.misc.srs560 import SRS560_Server

from kexp.config.ip import SRS_CONTROL_IP, SRS_SR560_SERVER_PORT, SRS_SR560_COM

def main():
    """Start the SRS560 server."""
    server = SRS560_Server(
        com_port=SRS_SR560_COM,
        server_ip=SRS_CONTROL_IP,
        server_port=SRS_SR560_SERVER_PORT)
    try:
        print("Starting SRS560 Server...")
        server.start()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        server.stop()

if __name__ == '__main__':
    main()