from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_snug(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)

        # self.xvar('beans',[0]*5)

        self.xvar('x_move',np.linspace(-6.,-3.25,20)*1.e-6)
        self.p.x_move = -3.5e-6
        # self.xvar('t_tweezer_single_move',np.linspace(3.,50.,20)*1.e-3)
        self.p.t_tweezer_single_move = 30.e-3

        self.p.frequency_tweezer_list = [73.7e6,77.3e6]

        a_list = [.46,.54]
        # a_list = [.7,.2]
        self.p.amp_tweezer_list = a_list

        self.p.t_amp_ramp = 1.e-3
        self.p.amp_final = .786

        self.p.t_tweezer_ramp_back_up = 100.e-3
        self.p.v_pd_ramp_back_up = 1.3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.tweezer.traps[1].cubic_move(t_move=self.p.t_tweezer_single_move,
                                         x_move=self.p.x_move,trigger=False)
        delay(100.e-3)
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        # tweezer evap 3 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_single_move)        

        delay(1.)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)