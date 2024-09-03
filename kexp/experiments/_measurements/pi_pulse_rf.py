from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class pi_pulse_rf(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.

        self.p.t_lightsheet_rampup = 5.e-3
        self.p.t_mot_load = 0.75

        # self.p.t_rabi = 313.79e-6 * 3
        
        # self.p.frequency_rf = 461.72e6 # (1,0) --> (2,0)
        
        # self.p.frequency_rf = 4.70820603e+08

        self.p.frequency_rf = 475.041709e6

        # self.xvar('frequency_rf',461.72e6 + np.linspace(-0.1,0.1,7)*1.e3)
        self.xvar('frequency_rf',461.72e6 + np.linspace(-0.1,0.1,7)*1.e3)
        # self.xvar('frequency_rf',462.42e6 + np.linspace(-25.,25.,10)*1.e3)
        # self.xvar('frequency_rf',475.19e6 + np.linspace(-10.,10.,5)*1.e3)
        # self.xvar('frequency_rf',475.041709e6 + np.linspace(-20.,20.,20)*1.e3)
        # self.xvar('t_rabi',np.linspace(0.,10000.,100)*1.e-6)
        self.xvar('t_rabi',np.linspace(0.,400.,6)*1.e-6)

        self.p.N_repeats = [1,2]

        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=6.,
                        v_yshim_current=self.p.v_yshim_current,
                          v_xshim_current=self.p.v_xshim_current)
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(20.e-3)
        
        if self.p.frequency_rf:
            self.rf.set_rf(frequency=self.p.frequency_rf)
            self.rf.on()
            delay(self.p.t_rabi)
            self.rf.off()
        
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        delay(7.e-3)
        self.lightsheet.off()
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


