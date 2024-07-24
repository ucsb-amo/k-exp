from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 1.
        # self.xvar('imaging_state',[2,1])
        # self.xvar('frequency_detuned_imaging',np.linspace(20.,80.,40)*1.e6)

        # self.xvar('t_lightsheet_hold',np.linspace(10.,2000.,20)*1.e-3)
        # self.xvar('t_lightsheet_rampup',np.linspace(100.,1000.,8)*1.e-3)
        # self.xvar('t_magtrap',np.linspace(0.,1000.,8)*1.e-3)
        # self.xvar('t_magtrap_ramp',np.linspace(12.,1000.,8)*1.e-3)
        # self.xvar('i_magtrap_ramp_end',np.linspace(20.,95.,8))
        # self.xvar('i_magtrap_init',np.linspace(10.,30.,8))
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.,9.,6))
        

        # self.xvar('t_tof',np.linspace(10.,200.,5)*1.e-6)
        self.p.t_lightsheet_hold = .1
        self.p.t_tof = 200.e-6

        # self.p.t_magtrap_ramp = 100.e-3
        
        # self.xvar('dummy',[0]*20)
        
        # self.p.v_pd_lightsheet_rampup_end = 0.638

        self.p.N_repeats = 1

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

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        for i in self.p.magtrap_rampdown_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_rampdown)

        self.inner_coil.off()

        delay(self.p.t_lightsheet_hold)

        self.ttl.pd_scope_trig.off()

        self.lightsheet.off()
    
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