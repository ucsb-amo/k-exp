import numpy as np
import os

from artiq.experiment import *
from artiq.language.core import kernel_from_string, now_mu, delay

from waxa.data import DataSaver
from waxa.config.img_types import img_types as img
# from waxx import Expt, img_types as img
from waxx.base.expt import Expt
from waxx.config.timeouts import INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT

from kexp.base import Devices, Cooling, Image, Cameras, Control, Clients
from kexp.config.camera_id import cameras
from kexp.config.ip import PATHS, server_talk
from kexp.config.data_vault import DataVault

from kexp.util.artiq.async_print import aprint

class Base(Expt, Devices, Cooling, Image, Cameras, Control, Clients):
    def __init__(self,
                 setup_camera=True,
                 save_data=True,
                 imaging_type=img.ABSORPTION,
                 absorption_image=None,
                 camera_select=cameras.xy_basler,
                 expt_params=None,
                 suppress_live_od=False):

        if suppress_live_od:
            setup_camera = False
            save_data = False

        super().__init__(setup_camera=setup_camera,
                         absorption_image=absorption_image,
                         save_data=save_data,
                         server_talk=server_talk)

        if expt_params == None:
            from kexp.config.expt_params import ExptParams
            self.params = ExptParams()
        else:
            self.params = expt_params

        self.p = self.params
        self.data = DataVault(self)
        
        self.prepare_devices(expt_params=self.params)

        self.ds = DataSaver(*PATHS, server_talk=server_talk)

        Clients.__init__(self, suppress_live_od=suppress_live_od)

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        self.finish_prepare_wax(N_repeats=N_repeats,shuffle=shuffle)

        self.dds.stash_defaults()

    @kernel
    def init_kernel(self, run_id = True,
                    init_dds =  True, 
                    init_dac = True,
                    dds_set = True, 
                    dds_off = True, 
                    init_sampler = True,
                    beat_ref_on=True):
        
        self.core.reset()

        # if self.setup_camera:
        #     self.wait_for_camera_ready(timeout=INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT)
        #     print("Camera is ready.")
        if run_id:
            print(self._ridstr) # prints run ID to terminal
        self.core.break_realtime()
        if init_dac:
            self.dac.dac_device.init() # initializes DAC
            delay(self.params.t_rtio)
            delay(1.e-3)
        if init_dds:
            self.init_all_cpld() # initializes DDS CPLDs
            self.init_all_dds() # initializes DDS channels
        if dds_set:
            delay(1*ms)
            self.dds.stash_defaults()
            self.set_all_dds() # set DDS to default values
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
        self.core.break_realtime()
        if init_sampler:
            self.sampler.init()
        
    @kernel
    def init_scan_kernel(self):

        self.arm_scopes()
        
        self.core.reset()
        
    @kernel
    def reset_devices(self):

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

    @kernel
    def cleanup_scan_kernel(self):

        self.cleanup_image_count()

        self.core.break_realtime()
        self.raman.clean_up_fast_frequency_update()

        # self.core.break_realtime()
        # self.reset_coils()

        self.core.break_realtime()

        self.cleanup_scan_kernel_wax()

    @kernel
    def post_scan(self):
        self.core.break_realtime()
        

    def end(self, expt_filepath, notify=True):
        self.end_wax(expt_filepath=expt_filepath, notify=notify)