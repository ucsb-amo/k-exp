import socket

class SLM:
    """Goal:
    A class to control the SLM. An object of this class will exist as an
    attribute of the experiment class (self.slm = SLM()). Then we can call SLM
    updates in line with experiment code with something like:
    

    self.slm.write_phase_spot(diameter = 200, phase = np.pi / 2, x_center
        = 100, y_center = 300)

    Break different elements into separate functions -- one to format a command,
    one to send a message to the SLM server, one that gets called by the command-line
    interface ("input" style), one that the user will call in experiments (like
    the "slm.write_phase_spot" example above).
    """    

    def __init__(self, server_ip='192.168.1.102', server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.default_x = 1920 // 2
        self.default_y = 1200 // 2

    def write_phase_spot(self, diameter, phase, x_center=None, y_center=None):
        """Sends a formatted phase spot command to the SLM server."""
        if x_center is None:
            x_center = self.default_x
        if y_center is None:
            y_center = self.default_y

        try:
            command = f"{diameter} {phase} {x_center} {y_center}"
            self._send_command(command)
            print(f"\nSent: {command}")
            print(f"-> diameter = {diameter} um, phase = {phase} pi, x-center = {x_center}, y-center = {y_center}\n")
        except Exception as e:
            print(f"Error sending phase spot: {e}")

    def _send_command(self, command):
        """Internal method to send the command over TCP."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.server_ip, self.server_port))
            client_socket.sendall(command.encode('utf-8'))

if __name__ == '__main__':
    slm = SLM()
