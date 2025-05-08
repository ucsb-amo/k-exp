import socket
from artiq.coredevice.core import Core
from artiq.language.core import now_mu, delay, kernel
from kexp.config.expt_params import ExptParams
import numpy as np

di = -1
dv = 1.
dm = 'spot'
SLM_RPC_DELAY = 2.

class SLM:
    """Goal:
    A class to control the SLM. An object of this class will exist as an
    attribute of the experiment class (self.slm = SLM()). Then we can call SLM
    updates in line with experiment code with something like:

    self.slm.write_phase_spot(dimension = 200, phase = np.pi / 2, x_center
        = 100, y_center = 300)
    """

    def __init__(self, expt_params = ExptParams(), core = Core,
                  server_ip='192.168.1.102', server_port=5000):
        
        self.server_ip = server_ip
        self.server_port = server_port
        self.params = expt_params
        self.core = core

    def write_phase_mask(self, dimension=dv, phase=dv, x_center=di, y_center=di, mask_type='spot'):
        """Writes a phase spot of given dimension and phase to the specified
        position on the slm display.

        Args:
            dimension (float): Diameter (in m) of the phase spot. If set to
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
        if dimension == dv:
            dimension = self.params.dimension_slm_mask
        if phase == dv:
            phase = self.params.phase_slm_mask
        if x_center == di:
            x_center = self.params.px_slm_phase_mask_position_x
        if y_center == di:
            y_center = self.params.px_slm_phase_mask_position_y
        if mask_type == dm:    
           mask_type =  self.params.slm_mask

        if mask_type == 'spot':
            mask = 1
        elif mask_type == 'grating':
            mask = 2
        elif mask_type == 'cross':
            mask = 3
        
        try:
            # note unit conversions, since the client uses units of um for
            # dimension and units of pi for phase
            dimension = int(dimension*1.e6)
            command = f"{int(dimension)} {phase/np.pi} {x_center} {y_center} {mask}"
            self._send_command(command)
            print(f"\nSent: {command}")
            print(f"-> mask: {mask_type}, dimension = {dimension} um, phase = {phase/np.pi} pi, x-center = {x_center}, y-center = {y_center}\n")
        except Exception as e:
            print(f"Error sending phase spot: {e}")

    @kernel
    def write_phase_mask_kernel(self, dimension=dv, phase=dv, x_center=di, y_center=di, mask_type=dm):
        """Writes a phase spot of given dimension and phase to the specified
        position on the slm display.

        Args:
            dimension (float): Dimension (in m) of the phase pattern, 
            e.g, diamteter for the spot and side length for the grating. 
            If set to zero, gives uniform phase pattern. Defaults to
            ExptParams.dimension_slm_spot.
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
        self.write_phase_mask(dimension, phase, x_center, y_center, mask_type=dm)
        delay(SLM_RPC_DELAY)

    def _send_command(self, command):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.server_ip, self.server_port))
            client_socket.sendall(command.encode('utf-8'))

if __name__ == '__main__':
    slm = SLM()
