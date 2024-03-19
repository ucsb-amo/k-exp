from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        
        self.xvar('imaging_state',[1,2])
        self.xvar('rf_yes',[0,1])
        # self.p.rf_yes = 1
        # self.xvar('t_wait',np.linspace(20,10.e3,10)*1.e-6)

        # self.params.frequency_mirny_carrier = 500.e6
        # self.p.frequency_rf_state_xfer_sweep_start = 450.7e6
        # self.p.frequency_rf_state_xfer_sweep_start = 470.7e6
        self.p.t_rf_state_xfer_sweep = 1000.e-3
        # self.p.dt_rf_state_xfer_sweep = 100.e-6

        self.p.t_mot_load = 1.

        self.p.N_repeats = [1,1]

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        self.load_2D_mot(self.p.t_2D_mot_load_delay)
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

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        
        if self.p.rf_yes:
            # self.rf.sweep()
            self.ttl.antenna_rf_sw.on()
            self.ttl.antenna_rf_sweep_trig.pulse(100.e-6)
            delay(2*s)
            self.ttl.antenna_rf_sw.off()
        else:
            # delay(self.p.t_rf_state_xfer_sweep)
            delay(2*s)

        self.lightsheet.off()
        
        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


