from artiq.experiment import *
from artiq.experiment import delay, delay_mu
import numpy as np
from kexp.config import ExptParams
from kexp.base.sub import Devices, Cooling, Image, Dealer, Cameras
from kexp.util.data import DataSaver, RunInfo

# also import the andor camera parameters

from kexp.util.artiq.async_print import aprint

class Base(Devices, Cooling, Image, Dealer, Cameras):
    def __init__(self,setup_camera=True,absorption_image=True,basler_imaging=True,andor_imaging=False):
        super().__init__()

        self.run_info = RunInfo(self)
        self._ridstr = " Run ID: "+ str(self.run_info.run_id)

        self.prepare_devices()

        self.choose_camera(setup_camera,absorption_image,basler_imaging,andor_imaging)
            
        self.params = ExptParams(camera_params=self.camera_params)

        self.images = []
        self.image_timestamps = []

        self.xvarnames = []
        self.sort_idx = []
        self.sort_N = []

        self.ds = DataSaver()

    def finish_build(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of build. Automatically adds repeats either if
        specified in N_repeats argument or if previously specified in
        self.params.N_repeats. Shuffles xvars if specified (defaults to True).
        Computes the number of images to be taken from the imaging method and
        the length of the xvar arrays.
        """

        self.params.compute_derived()

        if not self.xvarnames:
            self.xvarnames = ["dummy"]
            self.params.dummy = np.linspace(0,0,1)
        elif isinstance(self.xvarnames,str):
            self.xvarnames = [self.xvarnames]

        self.repeat_xvars(N_repeats=N_repeats)

        if shuffle:
            self.shuffle_xvars()

        self.get_N_img()

        # self.dds.cleanup_dds_ramps()

    @kernel
    def init_kernel(self, set_and_switch_off_dds = True, init_dac = True):
        print(self._ridstr) # prints run ID to terminal
        self.core.reset() # clears RTIO
        if init_dac:
            delay_mu(self.params.t_rtio_mu)
            self.zotino.init() # initializes DAC
            delay_mu(self.params.t_rtio_mu)
        if set_and_switch_off_dds:
            self.init_all_cpld() # initializes DDS CPLDs
            self.init_all_dds() # initializes DDS channels
            delay(1*ms)
            self.set_all_dds() # set DDS to default values
            self.switch_all_dds(0) # turn all DDS off to start experiment
        self.core.break_realtime() # add slack before scheduling experiment events

        self.set_imaging_detuning()


        
