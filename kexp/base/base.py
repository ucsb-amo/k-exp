import numpy as np

from artiq.experiment import *
from artiq.language.core import kernel_from_string, now_mu, delay

from waxx import Expt, img_types as img
from waxx.base import Monitor
from waxx.config.timeouts import INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT

from kexp.base import Devices, Cooling, Image, Cameras, Control
from kexp.config.camera_id import cameras
from kexp.config.ip import MONITOR_SERVER_IP, MONITOR_STATE_FILEPATH

from kexp.util.artiq.async_print import aprint

class Base(Expt, Devices, Cooling, Image, Cameras, Control):
    def __init__(self,
                 setup_camera=True,
                 save_data=True,
                 imaging_type=img.ABSORPTION,
                 absorption_image=None,
                 camera_select=cameras.xy_basler):

        super().__init__(setup_camera=setup_camera,
                         absorption_image=absorption_image,
                         save_data=save_data)

        from kexp.config.expt_params import ExptParams
        self.params = ExptParams()
        self.p = self.params

        self.monitor = Monitor(self,
                               monitor_server_ip=MONITOR_SERVER_IP,
                               device_state_json_path=MONITOR_STATE_FILEPATH)

        self.prepare_devices(expt_params=self.params)

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        self.finish_prepare_wax(N_repeats=N_repeats,shuffle=shuffle)

        self.dds.stash_defaults()
    
    def compute_new_derived(self):
        pass

    @kernel
    def init_kernel(self, run_id = True,
                    init_dds =  True, 
                    init_dac = True,
                    dds_set = True, 
                    dds_off = True):
        
        self.core.reset()

        if run_id:
            print(self._ridstr) # prints run ID to terminal
        self.core.break_realtime()
        if init_dac:
            self.dac.dac_device.init() # initializes DAC
            delay(self.params.t_rtio)
        self.core.break_realtime()
        if init_dds:
            self.init_all_cpld() # initializes DDS CPLDs
            self.init_all_dds() # initializes DDS channels
        if dds_set:
            delay(1*ms)
            self.set_all_dds() # set DDS to default values
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
        
    @kernel
    def init_scan_kernel(self,two_d_tweezers = False):

        self.core.reset()

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

    @kernel
    def cleanup_scan_kernel(self):
        pass