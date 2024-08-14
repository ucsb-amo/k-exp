from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class lightsheet_atom_count(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        self.p.t_magtrap = 30.e-3
        self.p.t_tof = 10.e-6
        self.p.t_lightsheet_rampup = 200.e-3
        self.p.t_lightsheet_hold = 100.e-3

        self.xvar('amp_imaging',np.logspace(np.log10(0.1),np.log10(0.5),30))

        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging,
                                  amp=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.gm(self.p.t_gm * s)

        self.ttl.pd_scope_trig.on()

        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        # magtrap start
        self.inner_coil.igbt_ttl.on()
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)

        # ramp up ligthsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)
        delay(30.e-3)

        self.inner_coil.off()
        self.ttl.pd_scope_trig.off()

        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()
    
        delay(self.p.t_tof)
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