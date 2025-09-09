import socket
from artiq.coredevice.core import Core
from artiq.language.core import now_mu, delay, kernel
from kexp.config.expt_params import ExptParams
import numpy as np
import threading
# from kexp.control.slm.PatternApp import Patternapp  # Assuming this file defines the PatternApp class
import tkinter as tk
import json
di = -1
dv = 1.
dm = 1
SLM_RPC_DELAY = 1.

class SLM:
    def __init__(self, expt_params=ExptParams(), core=Core,
                 server_ip='192.168.1.102', server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.params = expt_params
        self.core = core

    def write_phase_mask(self, dimension=dv, phase=dv, x_center=di, y_center=di, mask_type='spot', initialize=False):
        """Writes a phase spot of given dimension and phase to the specified
        position on the slm display.

        Args:
            dimension (float): Dimnesion (in m) of the phase mask. If set to
            zero, gives uniform phase pattern. Defaults to
            ExptParams.dimension_slm_mask.
            phase (float): Phase (in radians) for the phase mask. Defaults to
            ExptParams.phase_slm_mask.
            x_center (int): Horizontal position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1920. Defaults to
            ExptParams.px_slm_phase_mask_position_x.
            y_center (int): Vertical position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1200. Defaults to
            ExptParams.px_slm_phase_mask_position_y. 
            mask_type (str): The type of mask. It can be spot, grating or cross. 
            Defaults to ExptParams.slm_mask.
            initialize (booling): True for doing initialization on client side, and False 
            for letting SLM self-reinitialze automatically. 
        """        
        if dimension == dv:
            dimension = self.params.dimension_slm_mask
        if phase == dv:
            phase = self.params.phase_slm_mask
        if x_center == di:
            x_center = self.params.px_slm_phase_mask_position_x
        if y_center == di:
            y_center = self.params.px_slm_phase_mask_position_y

        x_center = int(x_center)
        y_center = int(y_center)

        if mask_type == 'spot':
            mask = 'spot'
        elif mask_type == 'grating':
            mask = 'grating'
        elif mask_type == 'cross':
            mask = 'cross'
        else:
            raise ValueError("mask_type must be one of 'spot', 'grating', or 'cross'.")

        try:
            dimension = int(dimension * 1.e6)
            command = {
                    "mask": mask,
                    "center": [x_center, y_center],
                    "phase": phase/np.pi,
                    "dimension": dimension,
                    "initialize": initialize
                }
            # command = f"{int(dimension)} {phase/np.pi} {x_center} {y_center} {mask}"
            self._send_command(command)
            print(f"\nSent: {command}")
            print(f"-> mask: {mask_type}, dimension = {dimension} um, phase = {phase/np.pi} pi, x-center = {x_center}, y-center = {y_center}\n")
        except Exception as e:
            print(f"Error sending phase spot: {e}")

    @kernel
    def write_phase_mask_kernel(self, dimension=dv, phase=dv, x_center=di, y_center=di, mask_type='spot',initialize=False):
        """Writes a phase spot of given dimension and phase to the specified
        position on the slm display.

        Args:
            dimension (float): Dimnesion (in m) of the phase mask. If set to
            zero, gives uniform phase pattern. Defaults to
            ExptParams.dimension_slm_mask.
            phase (float): Phase (in radians) for the phase mask. Defaults to
            ExptParams.phase_slm_mask.
            x_center (int): Horizontal position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1920. Defaults to
            ExptParams.px_slm_phase_mask_position_x.
            y_center (int): Vertical position (in pixels) of the
            phase spot (from top right). Indexed from 1 to 1200. Defaults to
            ExptParams.px_slm_phase_mask_position_y. 
            mask_type (str): The type of mask. It can be spot, grating or cross. 
            Defaults to ExptParams.slm_mask.
            initialize (booling): True for doing initialization on client side, and 
            False for letting SLM self-reinitialze automatically. 
        """    
        self.core.wait_until_mu(now_mu())
        self.write_phase_mask(dimension, phase, x_center, y_center, mask_type, initialize)
        delay(SLM_RPC_DELAY)

    def _send_command(self, command):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.server_ip, self.server_port))
            if isinstance(command, dict):
                command = json.dumps(command) # Convert dict to JSON string
            client_socket.sendall(command.encode('utf-8'))

    # def _launch_pattern_gui(self):
    #     root = tk.Tk()
    #     root.withdraw()
    #     Patternapp(root)
    #     root.mainloop()

if __name__ == '__main__':
    slm = SLM()
