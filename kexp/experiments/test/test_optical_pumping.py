from artiq.experiment import *
from artiq.experiment import delay, kernel
from kexp import Base, cameras
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from waxx.util.artiq.async_print import aprint

T32 = 1<<32
dv = 100.

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.xy_basler,
                      save_data=True)

        self.p.t_tof = 8.e-3

        # self.xvar('t_pump_to_F1',np.linspace(0.,100.,10)*1.e-6)

        # self.xvar('flash_repump_pre_img',[0,1])
        # self.p.flash_repump_pre_img = 1
        self.p.do_optical_pumping = 1
        # self.p.do_cooler_flash_after_op = 1
        self.xvar('do_optical_pumping',[0,1])
        self.xvar('do_cooler_flash_after_op',[0,1])
        self.p.flash_repump_pre_img = 1
        self.p.do_cooler_flash_after_op = 1

        # self.xvar('amp_d2_c_imaging',np.linspace(0.,0.15,5))

        self.p.pfrac_d1_c_d1cmot = 0.73
        self.p.pfrac_d1_c_gm = 0.7
        self.p.pfrac_d1_r_gm = 0.28
        self.p.pfrac_c_gmramp_end = 0.44
        self.p.pfrac_r_gmramp_end = 0.14

        self.p.t_magtrap_hold = 0.2

        self.p.N_repeats = 3
        self.p.t_mot_load = 0.5

        # self.p.amp_imaging = .35
        self.p.imaging_state = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.set_shims(v_zshim_current=self.params.v_zshim_current_magtrap,
                        v_yshim_current=self.params.v_yshim_current_magtrap,
                        v_xshim_current=self.params.v_xshim_current_magtrap)
        delay(2.e-3)
        self.dds.optical_pumping.set_dds()

        if self.p.do_optical_pumping:
            self.dds.optical_pumping.on()
            delay(self.p.t_optical_pumping)
            self.dds.optical_pumping.off()
        else:
            delay(self.p.t_optical_pumping)

        if self.p.do_cooler_flash_after_op:
            self.flash_cooler()
        else:
            delay(self.params.t_cooler_flash_imaging)

        # self.power_down_cooling()
        # delay(self.params.t_magtrap_delay)
        # self.inner_coil.on()
        
        # delay(self.p.t_magtrap_hold)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.inner_coil.snap_off()

        delay(self.p.t_tof)
        # if self.p.flash_repump_pre_img:
        #     self.flash_repump()
        # else:
        #     delay(self.p.t_repump_flash_imaging)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
