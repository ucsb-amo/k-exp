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

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,2.,6))
        # self.p.v_zshim_current_magtrap = 0.

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,5.,10))
        # self.p.v_xshim_current_magtrap = 0.

        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,9.5,10))
        # self.p.v_yshim_current_magtrap = 5.2

        # self.xvar('i_magtrap_init',np.linspace(18.,30.,10))
        # self.p.i_magtrap_init = 22.

        # self.xvar('t_lightsheet_rampup',np.linspace(100.,1000.,8)*1.e-3)

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.,9.,6))

        # self.xvar('t_magtrap_ramp',np.linspace(12.,2500.,8)*1.e-3)
        # self.p.t_magtrap_ramp = .367

        # self.xvar('i_magtrap_ramp_end',np.linspace(70.,95.,20))
        # self.p.i_magtrap_ramp_end = 88.

        # self.xvar('t_magtrap',np.linspace(0.001,2500.,8)*1.e-3)
        # self.p.t_magtrap = 1.4

        # self.xvar('t_tof',np.linspace(200.,800.,8)*1.e-6)
        self.p.t_lightsheet_hold = .1
        self.p.t_tof = 1000.e-6
        self.p.N_repeats = [1]

        # self.xvar('beans',[0,1])

        # self.p.t_magtrap_ramp = 100.e-3
        
        # self.xvar('dummy',[0]*20)

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
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        
        self.lightsheet.ramp(self.p.t_lightsheet_rampup,
                             self.p.v_pd_lightsheet_rampup_start,
                             self.p.v_pd_lightsheet_rampup_end)

        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)

        delay(self.p.t_magtrap)

        self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.,
                             n_steps=self.p.n_magtrap_ramp_steps)

        self.inner_coil.off()
        
        delay(self.p.t_lightsheet_hold)

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