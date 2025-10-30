import numpy as np

from artiq.experiment import *
from artiq.language.core import kernel_from_string, now_mu, delay

from waxx.config.timeouts import INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT

from kexp.base import Devices, Cooling, Image, Cameras, Control
from kexp.config.camera_id import cameras

from waxx import Expt, img_types as img

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

        self.prepare_devices(expt_params=self.params)

        self._polmod_config = self.choose_camera(setup_camera,imaging_type,camera_select)

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        self.finish_prepare_wax(N_repeats=N_repeats,shuffle=shuffle)

        self.configure_imaging_system(polmod_ao_bool=self._polmod_config)
        self.dds.stash_defaults()

        if self.tweezer.traps == []:
            self.tweezer.add_tweezer_list()
        self.tweezer.save_trap_list()
    
    def compute_new_derived(self):
        pass

    @kernel
    def init_kernel(self, run_id = True,
                    init_dds =  True, 
                    init_dac = True,
                    dds_set = True, 
                    dds_off = True, 
                    beat_ref_on=True,
                    init_shuttler = True, 
                    init_lightsheet = True,
                    setup_awg = True, 
                    setup_slm = True):
        
        self.core.reset()

        if self.setup_camera:
            self.wait_for_camera_ready(timeout=INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT)
            print("Camera is ready.")
        if setup_slm:
            self.setup_slm(self.run_info.imaging_type)
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
            self.imaging.init()
            self.set_imaging_detuning()
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
        if beat_ref_on:
            self.dds.beatlock_ref.on()
            self.dds.d1_beatlock_ref.on()
        if init_lightsheet:
            self.lightsheet.init()
        
    @kernel
    def init_scan_kernel(self,two_d_tweezers = False):
        
        self.core.reset()
        
        self.set_imaging_shutters()
        self.init_cooling()
        self.core.break_realtime()

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

        self.dds.d2_2dh_c.on()
        self.dds.d2_2dh_r.on()
        self.dds.d2_2dv_c.on()
        self.dds.d2_2dv_r.on()
        self.dds.push.on()

        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)
        self.dds.d1_beatlock_ref.set_dds(frequency=42.e6)

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_F1)
        elif self.p.imaging_state == 2.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)

        if self._setup_awg:
            if two_d_tweezers:
                self.tweezer.set_static_2d_tweezers(freq_list1=self.params.frequency_tweezer_list1,
                                                    freq_list2=self.params.frequency_tweezer_list2,
                                                    amp_list1=self.params.amp_tweezer_list1,
                                                    amp_list2=self.params.amp_tweezer_list2)
            self.tweezer.reset_traps(self.xvarnames)
            delay(100.e-3)
            self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        
        self.tweezer.pid1_int_hold_zero.pulse(1.e-6)
        self.tweezer.pid1_int_hold_zero.on()
        
        # self.dds.ry_405_switch.on()
        # self.dds.ry_980_switch.on()
        
        self.dds.d1_beatlock_ref.on()

    @kernel
    def cleanup_scan_kernel(self):
        self.cleanup_image_count()
        self.reset_coils()
        self.ttl.line_trigger.clear_input_events()