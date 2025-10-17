from artiq.experiment import *
from artiq.experiment import delay, delay_mu
import numpy as np

from artiq.language.core import kernel_from_string, now_mu

RPC_DELAY = 10.e-3

from kexp.base import Devices, Cooling, Image, Cameras, Control
from waxx.config.timeouts import INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT

from waxx import Expt, img_types as img

class Base(Expt, Devices, Cooling, Image, Cameras, Control):
    def __init__(self,
                 setup_camera=True,
                 save_data=True,
                 imaging_type=img.ABSORPTION,
                 absorption_image=None,
                 camera_select="xy_basler"):

        super().__init__(setup_camera=setup_camera,
                         absorption_image=absorption_image,
                         save_data=save_data)

        from kexp.config.expt_params import ExptParams
        self.params = ExptParams()
        self.p = self.params

        self.prepare_devices(expt_params=self.params)

        self.choose_camera(setup_camera,imaging_type,camera_select)

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        self.finish_prepare_wax()
    
    def compute_new_derived(self):
        pass

    @kernel
    def init_kernel(self, run_id = True,
                    init_dds =  True, 
                    init_dac = True,
                    dds_set = True, 
                    dds_off = True):
        if self.setup_camera:
            self.wait_for_camera_ready(timeout=INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT)
            print("Camera is ready.")
        if run_id:
            print(self._ridstr) # prints run ID to terminal
        self.core.reset() # clears RTIO
        if init_dac:
            self.dac.dac_device.init() # initializes DAC
            delay(self.params.t_rtio)
            self.core.break_realtime()
        if init_dds:
            self.init_all_cpld() # initializes DDS CPLDs
            self.init_all_dds() # initializes DDS channels
            self.core.break_realtime()
        if dds_set:
            delay(1*ms)
            self.set_all_dds() # set DDS to default values
            self.core.break_realtime()
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
            self.core.break_realtime()
        
    @kernel
    def init_scan_kernel(self):
        
        self.core.break_realtime()

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

    @kernel
    def cleanup_scan_kernel(self):
        self.cleanup_image_count()
        self.ttl.line_trigger.clear_input_events()