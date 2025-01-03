from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.v_pd_lightsheet_rampup_end = 9.99
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.5,9.99,5))
        # self.xvar('v_lightsheet_paint_amp_max',np.arange(-7.,6.,1))
        # self.xvar('t_lightsheet_rampup',np.linspace(0.1,3.,8))

        # self.xvar('t_magtrap_ramp',np.linspace(.05,2.,10))

        self.xvar('frequency_ao_ry_405', np.arange(171.9,221.9,.5)*1.e6)
        self.p.frequency_ao_ry_405 = 206.09*1.e6

        self.p.t_lightsheet_hold = 10.e-3

        self.p.t_ry_pulse = 20.e-6
        # self.xvar('t_ry_pulse', np.linspace(10,50,5)*1.e-3)

        # self.xvar('t_tof',np.linspace(50.,1000.,10)*1.e-6)
        self.p.t_tof = 20.e-6
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.dds.ry_405.set_dds(amplitude=0.)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet()

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        self.dds.ry_405.set_dds(frequency=self.p.frequency_ao_ry_405, amplitude=.245)
        
        

        self.lightsheet.off()

        self.dds.ry_405.on()
        delay(self.p.t_ry_pulse)
        
        self.dds.ry_405.off()

        # delay(self.p.t_tof)
        self.flash_repump()
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