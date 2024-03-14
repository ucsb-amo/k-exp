from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        
        self.xvar('imaging_state',[1,2])
        self.xvar('t_wait',np.linspace(20,20.e3,2)*1.e-6)

        self.p.t_mot_load = 1.

        self.finish_build()

    @kernel
    def scan_kernel(self):

        self.dds.d1_3d_c.dds_device.init()
        self.dds.d2_3d_c.dds_device.init()
        self.dds.d2_3d_r.dds_device.init()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()
        self.dds.d1_3d_c.dds_device.power_down()
        self.dds.d2_3d_c.dds_device.power_down()
        self.dds.d2_3d_r.dds_device.power_down()

        self.flash_cooler()

        if self.p.rf_yes:
            self.ttl.antenna_rf_sw.on()
            self.ttl.antenna_rf_sweep_trig.pulse(t=100.e-6)
            delay(9.e-3)
            self.ttl.antenna_rf_sw.off()
        else:
            delay(9.e-3)
            
        delay(self.p.t_wait)
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


