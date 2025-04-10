import socket
from artiq.coredevice.core import Core
from artiq.language.core import now_mu, delay, kernel
from kexp.config.expt_params import ExptParams
import numpy as np

di = -1
dv = 1.
SLM_RPC_DELAY = 5.

class SLM:
    """Goal:
    A class to control the SLM. An object of this class will exist as an
    attribute of the experiment class (self.slm = SLM()). Then we can call SLM
    updates in line with experiment code with something like:

    self.slm.write_phase_spot(diameter = 200, phase = np.pi / 2, x_center
        = 100, y_center = 300)
    """

    def __init__(self, expt_params = ExptParams(), core = Core(),
                  server_ip='192.168.1.102', server_port=5000):
        
        self.server_ip = server_ip
        self.server_port = server_port
        self.params = expt_params
        self.core = core

    def write_phase_spot(self, diameter=dv, phase=dv, x_center=di, y_center=di):
        """Writes a phase spot of given diameter and phase to the specified
        position on the slm display.

        Args:
            diameter (float): Diameter (in m) of the phase spot. If set to
            zero, gives uniform phase pattern. Defaults to
            ExptParams.diameter_slm_spot.
            phase (float): Phase (in radians) for the phase spot. Defaults to
            ExptParams.phase_slm_spot.
            x_center (int): Horizontal position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1920. Defaults to
            ExptParams.px_slm_phase_spot_position_x.
            y_center (int): Vertical position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1200. Defaults to
            ExptParams.px_slm_phase_spot_position_y. 
        """        
        if diameter == dv:
            diameter = self.params.diameter_slm_spot
        if phase == dv:
            phase = self.params.phase_slm_spot
        if x_center == di:
            x_center = self.params.px_slm_phase_spot_position_x
        if y_center == di:
            y_center = self.params.px_slm_phase_spot_position_y

        try:
            # note unit conversions, since the client uses units of um for
            # diameter and units of pi for phase
            command = f"{int(diameter*1.e6)} {phase/np.pi} {x_center} {y_center}"
            self._send_command(command)
            print(f"\nSent: {command}")
            print(f"-> diameter = {diameter} um, phase = {phase} pi, x-center = {x_center}, y-center = {y_center}\n")
        except Exception as e:
            print(f"Error sending phase spot: {e}")

    @kernel
    def write_phase_spot_kernel(self, diameter=dv, phase=dv, x_center=di, y_center=di):
        """Writes a phase spot of given diameter and phase to the specified
        position on the slm display.

        Args:
            diameter (float): Diameter (in m) of the phase spot. If set to
            zero, gives uniform phase pattern. Defaults to
            ExptParams.diameter_slm_spot.
            phase (float): Phase (in radians) for the phase spot. Defaults to
            ExptParams.phase_slm_spot.
            x_center (int): Horizontal position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1920. Defaults to
            ExptParams.px_slm_phase_spot_position_x.
            y_center (int): Vertical position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1200. Defaults to
            ExptParams.px_slm_phase_spot_position_y. 
        """    
        self.core.wait_until_mu(now_mu())
        self.write_phase_spot(diameter,phase,x_center,y_center)
        delay(SLM_RPC_DELAY)

    def _send_command(self, command):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.server_ip, self.server_port))
            client_socket.sendall(command.encode('utf-8'))

if __name__ == '__main__':
    slm = SLM()
