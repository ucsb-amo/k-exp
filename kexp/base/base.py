from artiq.experiment import *
from artiq.experiment import delay, delay_mu
import numpy as np
from kexp.config import ExptParams
from kexp.base.sub import Devices, Cooling, Image, Dealer, Cameras, Scanner
from kexp.util.data import DataSaver, RunInfo

# also import the andor camera parameters

from kexp.util.artiq.async_print import aprint

@portable
def nothing():
    pass

class Base(Devices, Cooling, Image, Dealer, Cameras, Scanner):
    def __init__(self,setup_camera=True,absorption_image=True,camera_select="xy_basler"):
        Scanner.__init__(self)
        super().__init__()

        self.run_info = RunInfo(self)
        self._ridstr = " Run ID: "+ str(self.run_info.run_id)

        self.params = ExptParams()
        self.compute_new_derived = nothing

        self.prepare_devices(expt_params=self.params)

        self.choose_camera(setup_camera,absorption_image,camera_select)

        self.images = []
        self.image_timestamps = []

        self.xvarnames = []
        self.sort_idx = []
        self.sort_N = []

        self.ds = DataSaver()

    def finish_build(self,N_repeats=[],shuffle=True,cleanup_dds_profiles=True,
                     compute_new_derived=nothing):
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
        if compute_new_derived == nothing:
            compute_new_derived = self.compute_new_derived
        else:
            self.compute_new_derived = compute_new_derived

        if not self.xvarnames:
            self.xvar("dummy",[0])

        self.repeat_xvars(N_repeats=N_repeats)

        if shuffle:
            self.shuffle_xvars()

        self.get_N_img()

        if cleanup_dds_profiles:
            self.dds.cleanup_dds_profiles()

        self.params.compute_derived()
        self.compute_new_derived()
        self.generate_assignment_kernels()

    @kernel
    def init_kernel(self, run_id = True, init_dds = True, init_dac = True, dds_set = True, dds_off = True, beat_ref_on=True):
        if run_id:
            print(self._ridstr) # prints run ID to terminal
        self.core.reset() # clears RTIO
        if init_dac:
            delay_mu(self.params.t_rtio_mu)
            self.dac.dac_device.init() # initializes DAC
            delay_mu(self.params.t_rtio_mu)
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
        self.core.break_realtime() # add slack before scheduling experiment events