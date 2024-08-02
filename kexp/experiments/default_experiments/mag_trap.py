from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='z_basler',save_data=True)

        self.p.imaging_state = 1.

        # self.xvar('frequency_detuned_imaging',np.arange(400.,450.,3)*1.e6)
        # self.p.frequency_detuned_imaging = 433.e6 # 150a0
        # self.p.frequency_detuned_imaging = 428.e6 # 150a0
        # self.p.frequency_detuned_imaging = 412.e6 # NI

        self.p.t_mot_load = .75

        # self.xvar('t_tof',np.linspace(.02,5.,6)*1.e-3)
        self.p.t_tof = 20.e-6
        self.p.N_repeats = [1]
        
        self.xvar('dummy_z',[0]*50)

        # self.xvar('amp_imaging',np.linspace(.2,.5,15))
        self.camera_params.amp_imaging = .4
        
        # self.camera_params.amp_imaging = 0.106
        self.camera_params.exposure_time = 20.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.amp_imaging = 0.106

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)

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

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.inner_coil.on()

        delay(self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        # for i in self.p.magtrap_rampdown_list:
        #     self.inner_coil.set_current(i_supply=i)
        #     delay(self.p.dt_magtrap_rampdown)

        self.inner_coil.off()

        delay(self.p.t_tof)
        # self.flash_repump()
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
