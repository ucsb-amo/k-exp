
from artiq.experiment import *
from artiq.experiment import delay, delay_mu
import numpy as np
from kexp.config.expt_params import ExptParams
from kexp.base.sub import Devices, Cooling, Image, Dealer, Cameras, Scanner, Scribe
from kexp.util.data.data_vault import DataSaver
from kexp.util.data.run_info import RunInfo
from kexp.util.data import server_talk
from artiq.language.core import kernel_from_string, now_mu
import time

RPC_DELAY = 10.e-3

# also import the andor camera parameters

from kexp.util.artiq.async_print import aprint

class Base(Devices, Cooling, Image, Dealer, Cameras, Scanner, Scribe):
    def __init__(self,setup_camera=True,absorption_image=True,save_data=True,camera_select="xy_basler"):
        Scanner.__init__(self)
        super().__init__()

        self.setup_camera = setup_camera
        self.run_info = RunInfo(self,save_data)
        self._ridstr = " Run ID: "+ str(self.run_info.run_id)

        self.params = ExptParams()
        self.p = self.params

        self.prepare_devices(expt_params=self.params)

        self.choose_camera(setup_camera,absorption_image,camera_select)

        self.images = []
        self.image_timestamps = []

        self.xvarnames = []
        self.sort_idx = []
        self.sort_N = []

        self._setup_awg = False

        self.ds = DataSaver()

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare. 
        
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

        if self.run_info.absorption_image:
            if self.params.N_pwa_per_shot > 1:
                print("You indicated more than one PWA per shot, but the analysis is set to absorption imaging. Setting # PWA to 1.")
            self.params.N_pwa_per_shot = 1

        if not self.xvarnames:
            self.xvar("dummy",[0]*2)
        if self.xvarnames and not self.scan_xvars:
            for key in self.xvarnames:
                self.xvar(key,vars(self.params)[key])
        
        self.repeat_xvars(N_repeats=N_repeats)
        
        if shuffle:
            self.shuffle_xvars()
        
        self.params.N_img = self.get_N_img()
        self.prepare_image_array()

        # if cleanup_dds_profiles:
        #     self.dds.cleanup_dds_profiles()

        self.params.compute_derived()
        self.compute_new_derived()

        if self.tweezer.traps == []:
            self.tweezer.add_tweezer_list()
        self.tweezer.save_trap_list()

        if self.setup_camera:
            self.data_filepath = self.ds.create_data_file(self)

        self.generate_assignment_kernels()
    
    def compute_new_derived(self):
        pass

    @kernel
    def init_kernel(self, run_id = True, init_dds =  True, init_dac = True,
                     dds_set = True, dds_off = True, beat_ref_on=True,
                     init_shuttler = True, init_lightsheet = True, setup_awg = True):
        if self.setup_camera:
            self.wait_for_camera_ready(timeout=15.)
            print("Camera is ready.")
        if run_id:
            print(self._ridstr) # prints run ID to terminal
        if setup_awg:
            self._setup_awg = setup_awg
            self.tweezer.awg_init()
        self.core.reset() # clears RTIO
        if init_dac:
            self.dac.dac_device.init() # initializes DAC
            delay(self.params.t_rtio)
        if init_shuttler:
            self.shuttler.init()
            self.core.break_realtime()
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
            self.dds.d1_beatlock_ref.on()
        if init_lightsheet:
            self.lightsheet.init()

        # self.dds.ry_405.on()
        self.dds.ry_980.on()
        
    @kernel
    def init_scan_kernel(self):
        
        self.dds.init_cooling()
        self.core.break_realtime()

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)

        # self.dds.ry_405.on()
        self.dds.ry_980.on()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_F1)
        elif self.p.imaging_state == 2.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)

        if self._setup_awg:
            self.tweezer.reset_traps(self.xvarnames)
            delay(100.e-3)
            self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        
        self.tweezer.pid1_int_hold_zero.pulse(1.e-6)
        self.tweezer.pid1_int_hold_zero.on()

    @kernel
    def cleanup_scan_kernel(self):
        if not self.run_info.absorption_image:
            delay(self.params.t_light_only_image_delay)
            self.light_image()
            delay(self.params.t_dark_image_delay)
            self.dark_image()

    def prepare_image_array(self):
        if self.run_info.save_data:
            print(self.camera_params.camera_type)
            if self.camera_params.camera_type == 'andor':
                dtype = np.uint16
            elif self.camera_params.camera_type == 'basler':
                dtype = np.uint8
            else:
                dtype = np.uint8
            self.images = np.zeros((self.params.N_img,)+self.camera_params.resolution,dtype=dtype)
            self.image_timestamps = np.zeros((self.params.N_img,))
            # self.image_timestamps = np.empty((self.params.N_img,),dtype=type(time.time()))
        else:
            self.images = np.array([0])
            self.image_timestamps = np.array([0])

    def end(self,expt_filepath):

        # self.tweezer.close()
        
        if self.setup_camera:
            if self.run_info.save_data:
                self.cleanup_scanned()
                self.write_data(expt_filepath)
            else:
                self.remove_incomplete_data()
        server_talk.play_random_sound()