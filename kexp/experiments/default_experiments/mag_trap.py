from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mag_trap(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.xvar('frequency_detuned_imaging',np.linspace(440.,500.,40)*1.e6)

        self.p.t_magtrap_hold = 100.e-3
        # self.xvar('t_tof',np.linspace(4.,12.,15)*1.e-3)
        # self.xvar('i_magtrap_init',np.linspace(20.,34.,8))
        # self.xvar('i_magtrap_ramp_start',np.linspace(28.,95.,8))
        # self.xvar('t_magtrap',np.linspace(0.,20.,8)*1.e-3)
        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,8.,20))

        self.p.t_tof = 5.e-3

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

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.ttl.pd_scope_trig.on()

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)
        
        self.inner_coil.on()

        delay(self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(20.e-3)        

        self.inner_coil.off()

        self.ttl.pd_scope_trig.off()
    
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