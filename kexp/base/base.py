import numpy as np
import os

from artiq.experiment import *
from artiq.language.core import kernel_from_string, now_mu, delay

from waxa.data import DataSaver
from waxx import Expt, img_types as img
from waxx.config.timeouts import INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT

from kexp.base import Devices, Cooling, Image, Cameras, Control, Clients
from kexp.config.camera_id import cameras
from kexp.config.ip import PATHS, server_talk
from kexp.config.data_vault import DataVault

from waxx.util.live_od.camera_client import CameraClient
from kexp.config.ip import CAMERA_SERVER_IP, CAMERA_SERVER_PORT

from kexp.util.artiq.async_print import aprint

class Base(Expt, Devices, Cooling, Image, Cameras, Control, Clients):
    def __init__(self,
                 setup_camera=True,
                 save_data=True,
                 imaging_type=img.ABSORPTION,
                 absorption_image=None,
                 camera_select=cameras.xy_basler,
                 expt_params=None):

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

        self.prepare_devices(expt_params=self.params)

        _img_config = self.choose_camera(setup_camera,imaging_type,camera_select)
        self.configure_imaging_system(imaging_configuration=_img_config)

        self.data = DataVault(self)
        self.ds = DataSaver(*PATHS,server_talk=server_talk)

        Clients.__init__(self)

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        self.finish_prepare_wax(N_repeats=N_repeats,shuffle=shuffle)

        # self.configure_imaging_system(polmod_ao_bool=self._polmod_config)
        self.dds.stash_defaults()

        if self.tweezer.traps == []:
            self.tweezer.add_tweezer_list()
        self.tweezer.save_trap_list()

    @kernel
    def init_kernel(self, 
                    notify_server=True,
                    run_id = True,
                    init_dds =  True, 
                    init_dac = True,
                    dds_set = True, 
                    dds_off = True, 
                    init_sampler = True,
                    init_imaging = True,
                    beat_ref_on=True,
                    init_shuttler = True, 
                    init_lightsheet = True,
                    setup_awg = True, 
                    setup_slm = True,
                    init_magnets = True,
                    init_ry = True):
        
        self.core.reset()
        self.init_kernel_wax(notify_server=notify_server)

        self.core.wait_until_mu(now_mu())
        if setup_slm:
            self.setup_slm(self.run_info.imaging_type)
        if run_id:
            print(self._ridstr) # prints run ID to terminal
        if setup_awg:
            self._setup_awg = setup_awg
            self.tweezer.awg_init()
        self.core.break_realtime()
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
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
        self.core.break_realtime()
        if init_imaging:
            self.imaging.init()
            self.set_imaging_detuning()
            self.imaging.set_power(self.camera_params.amp_imaging)
        if init_sampler:
            self.sampler.init()
        if beat_ref_on:
            self.dds.beatlock_ref.on()
            # self.dds.d1_beatlock_ref.on()
        if init_lightsheet:
            self.lightsheet.init()
        if init_magnets:
            self.outer_coil.off()
            self.inner_coil.off()
        # if init_ry:
            # self.ry_405.init()
        
    @kernel
    def init_scan_kernel(self,two_d_tweezers = False):

        self.arm_scopes()
        self.read_magnetometer()
        
        self.core.reset()
        self.reset_devices()
        self.reset_tweezers(two_d_tweezers)

    @kernel
    def reset_devices(self):
        # 2D MOT current back on
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)
        
        self.init_cooling()
        self.core.break_realtime()

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

        # turn on 2D MOT beams
        self.dds.d2_2dh_c.on()
        self.dds.d2_2dh_r.on()
        self.dds.d2_2dv_c.on()
        self.dds.d2_2dv_r.on()
        self.dds.push.on()

        # reset imaging detuning, power
        self.set_imaging_shutters()
        delay(10.e-3)
        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_F1)
        elif self.p.imaging_state == 2.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
        self.imaging.set_power(self.camera_params.amp_imaging,
                                reset_pid=False)

    @kernel
    def cleanup_scan_kernel(self):
        self.cleanup_image_count()

        self.core.break_realtime()
        self.reset_coils()

        self.core.break_realtime()
        self.ttl.line_trigger.clear_input_events()

        self.cleanup_scan_kernel_wax()

    @kernel
    def post_scan(self):
        self.background_field()

    @kernel
    def end(self, expt_filepath):
        self.end_wax(expt_filepath=expt_filepath)