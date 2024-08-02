from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

T32 = 1<<32

class magtrap_mloop_test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.frequency_detuned_imaging = 424.e6 

        self.p.t_mot_load = .75

        # self.xvar("t_tof", np.linspace(0.1,10,20)*1.e-3)
        self.p.t_tof = 200.e-6

        self.xvar("t_magtrap", np.linspace(0.01,1,20))
        self.p.t_magtrap = 0.5

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.inner_coil.on()

        delay(self.p.t_lightsheet_rampup)

        # for i in self.p.magtrap_ramp_list:
        #     self.inner_coil.set_current(i_supply=i)
        #     delay(self.p.dt_magtrap_ramp)
        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)
        
        delay(self.p.t_magtrap)
        
        self.inner_coil.off()


        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)