from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class field_0_magnetometry(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.p.t_rf_state_xfer_sweep = 10.e-3
        self.p.n_rf_state_xfer_sweep_steps = 100
        self.p.frequency_rf_sweep_state_prep_fullwidth = 10.204e3
        self.p.do_sweep = 1

        # self.xvar('v_yshim_current_gm', np.linspace(1.6,2.2,5))
        # self.xvar('v_xshim_current_gm', np.linspace(0.,.2,5))
        # self.xvar('v_zshim_current_gm', np.linspace(0.735,.77,5))

        self.xvar('frequency_rf_sweep_state_prep_center', 461.7e6 + np.linspace(-.25,.25,50)*1.e6)

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

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
        
        self.set_shims(v_zshim_current=.75,
                        v_yshim_current=1.75,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.flash_cooler()

        self.dds.power_down_cooling()

        # self.set_shims(v_zshim_current=0.,
        #                v_yshim_current=self.p.v_zshim_current_gm,
        #                 v_xshim_current=self.p.v_zshim_current_gm)
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        delay(100*ms)
        if self.p.do_sweep:
            self.rf.sweep(frequency_sweep_list=self.p.frequency_rf_sweep_state_prep_list)

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