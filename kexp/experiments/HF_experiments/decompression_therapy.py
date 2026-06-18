
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2, tweezer_vpd2_to_vpd1

class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('ramp_painting_off',[0,1])
        self.p.ramp_painting_off = 1
        self.p.ramp_painting_on = 0

        # self.xvar('t_tof',np.linspace(10.,200.,10)*1.e-6)
        self.p.t_tof = 500.e-6

        # self.xvar('t_tweezer_paint_rampdown', np.linspace(0.,10.,7)*1.e-3)
        # self.p.t_tweezer_paint_rampdown = 50.e-3
        self.p.t_tweezer_repaint = 0.
        self.p.t_tweezer_hold = 5.e-3

        self.xvar('t_tweezer_squeezer_ramp_2', np.linspace(5.,50.,7)*1.e-3)
        self.p.t_tweezer_squeezer_ramp_2 = 20.e-3

        self.p.v_pd_hf_tweezer_squeeze_power = 3.97

        # self.xvar('compress',[0,1])
        self.p.compress = 1
        # self.xvar('decompress',[0,1])
        self.p.decompress = 1

        self.camera_params.amp_imaging = 0.3

        self.p.N_repeats = 5
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def decompress(self):

        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_2,
                          v_start=self.p.v_pd_hf_tweezer_squeeze_power,
                          v_end=tweezer_vpd2_to_vpd1(self.p.v_pd_tweezer_squeeze_rampup_handoff_lp),
                          paint=False,keep_trap_frequency_constant=False,
                          cubic_ramp=True)
        
        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_1,
                          v_start=self.p.v_pd_tweezer_squeeze_rampup_handoff_lp,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                          low_power=True, paint=False, keep_trap_frequency_constant=False,
                          cubic_ramp=True)
            
    @kernel
    def ramp_off_painting(self):
        if self.p.t_tweezer_paint_rampdown == 0:
            self.tweezer.paint_amp_dac.set(-7.)
        else:
            v0 = self.tweezer.paint_amp_dac.v
            self.tweezer.paint_amp_dac.cubic_ramp(t=self.p.t_tweezer_paint_rampdown,
                                                  v_start=v0,
                                                  v_end=-7.,
                                                  n=100)
    
    @kernel
    def ramp_on_painting(self, v_paint_f):
        if self.p.t_tweezer_repaint == 0.:
            self.tweezer.paint_amp_dac.set(v_paint_f)
        else:
            self.tweezer.paint_amp_dac.cubic_ramp(t=self.p.t_tweezer_repaint,
                                                    v_start=-7.,
                                                    v_end=v_paint_f,
                                                    n=100)
            
    @kernel
    def tweezer_squeeze_2(self, cubic_ramp=True):
        
        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_1,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                          v_end=self.p.v_pd_tweezer_squeeze_rampup_handoff_lp,
                          low_power=True, paint=False, keep_trap_frequency_constant=False,
                          cubic_ramp=cubic_ramp)

        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_2,
                          v_start=tweezer_vpd2_to_vpd1(self.p.v_pd_tweezer_squeeze_rampup_handoff_lp),
                          v_end=self.p.v_pd_hf_tweezer_squeeze_power,
                          paint=False,keep_trap_frequency_constant=False,
                          cubic_ramp=cubic_ramp)

    @kernel
    def scan_kernel(self):

        self.p.t_tweezer_repaint = self.p.t_tweezer_paint_rampdown

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)
        self.prepare_hf_tweezers(squeeze=False)

        v0 = self.tweezer.paint_amp_dac.v

        if self.p.ramp_painting_off:
            self.ramp_off_painting()

        if self.p.compress:
            self.tweezer_squeeze_2()
        
            if self.p.decompress:
                self.decompress()

        if self.p.ramp_painting_on:
            self.ramp_on_painting(v0)
        
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

