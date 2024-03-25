from artiq.experiment import *
from artiq.experiment import delay, delay_mu
import numpy as np
from kexp.config import ExptParams
from kexp.base.sub import Devices, Cooling, Image, Dealer, Cameras, Scanner, Scribe
from kexp.util.data import DataSaver, RunInfo

# also import the andor camera parameters

from kexp.util.artiq.async_print import aprint

class Base(Devices, Cooling, Image, Dealer, Cameras, Scanner, Scribe):
    def __init__(self,setup_camera=True,absorption_image=True,camera_select="xy_basler"):
        Scanner.__init__(self)
        super().__init__()

        self.setup_camera = setup_camera
        self.run_info = RunInfo(self)
        self._ridstr = " Run ID: "+ str(self.run_info.run_id)

        self.params = ExptParams()
        self.p = self.params
        self.compute_new_derived = self.nothing

        self.prepare_devices(expt_params=self.params)

        self.choose_camera(setup_camera,absorption_image,camera_select)

        self.images = []
        self.image_timestamps = []

        self.xvarnames = []
        self.sort_idx = []
        self.sort_N = []

        self.ds = DataSaver()

    def finish_build(self,N_repeats=[],shuffle=True,cleanup_dds_profiles=True):
        """
        To be called at the end of build. 
        
        Automatically adds repeats either if specified in N_repeats argument or
        if previously specified in self.params.N_repeats. 
        
        Shuffles xvars if specified (defaults to True). Computes the number of
        images to be taken from the imaging method and the length of the xvar
        arrays.

        Computes derived parameters within ExptParams.

        Accepts an additional compute_derived method that is user defined in the
        experiment file. This is to allow for recomputation of derived
        parameters that the user created in the experiment file at each step in
        a scan. This must be an RPC -- no kernel decorator.
        """
        if not self.xvarnames:
            self.xvar("dummy",[0])
        if self.xvarnames and not self.scan_xvars:
            for key in self.xvarnames:
                self.xvar(key,vars(self.params)[key])
        
        self.repeat_xvars(N_repeats=N_repeats)
        
        if shuffle:
            self.shuffle_xvars()
        
        self.params.N_img = self.get_N_img()
        self.prepare_image_array()

        if cleanup_dds_profiles:
            self.dds.cleanup_dds_profiles()

        self.params.compute_derived()
        self.compute_new_derived()

        self.data_filepath = self.ds.create_data_file(self)

        self.generate_assignment_kernels()

        if self.setup_camera:
            self.wait_for_camera_ready(timeout=10.)
            print("Camera is ready.")

    @kernel
    def init_kernel(self, run_id = True, init_dds = True, init_dac = True,
                     dds_set = True, dds_off = True, beat_ref_on=True,
                     init_rf = True):
        if run_id:
            print(self._ridstr) # prints run ID to terminal
        self.core.reset() # clears RTIO
        delay(1*s)
        if init_dac:
            delay(self.params.t_rtio)
            self.dac.dac_device.init() # initializes DAC
            delay(self.params.t_rtio)
        if init_dds:
            self.init_all_cpld() # initializes DDS CPLDs
            self.init_all_dds() # initializes DDS channels
        if dds_set:
            delay(1*ms)
            self.set_all_dds() # set DDS to default values
            self.set_imaging_detuning()
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
        if beat_ref_on:
            self.dds.beatlock_ref.on()
        if init_rf:
            self.rf.init()
        self.core.break_realtime() # add slack before scheduling experiment events

    def prepare_image_array(self):
        print(self.camera_params.camera_type)
        if self.camera_params.camera_type == 'andor':
            dtype = np.uint16
        elif self.camera_params.camera_type == 'basler':
            dtype = np.uint8
        else:
            dtype = np.uint8
        self.images = np.zeros((self.params.N_img,)+self.camera_params.resolution,dtype=dtype)
        self.image_timestamps = np.zeros((self.params.N_img,))

    def end(self,expt_filepath):
        if self.setup_camera:
            self.cleanup_scanned()
            self.write_data(expt_filepath)
