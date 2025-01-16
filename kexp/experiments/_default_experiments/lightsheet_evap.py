from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_evap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.imaging_state = 1.

        self.p.t_tof = 40.e-6
        # self.xvar('t_tof',[10*1.e-6]*100)
        # self.xvar('t_tof',np.linspace(10.,100.,10)*1.e-6)

        # self.xvar('detune_d1_c_gm',np.linspace(1.,10.,8))
        # self.xvar('detune_d1_r_gm',np.linspace(1.,10.,8))

        self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.6,8))
        self.xvar('pfrac_r_gmramp_end',np.linspace(.05,.6,8))

        # self.xvar('t_lightsheet_rampdown',np.linspace(.05,1.,8))
        # self.p.t_lightsheet_rampdown = .6

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,8.,20))
        self.p.v_pd_lightsheet_rampdown_end = 5.8

        # self.p.t_lightsheet_rampup = 1.
        # self.p.t_magtrap_ramp = 1.

        # self.xvar('i_evap1_current',np.linspace(196.,199.,8))
        # self.p.i_evap1_current = 198.

        self.p.N_repeats = 1
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.set_high_field_imaging(i_outer=self.p.i_evap1_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # # feshbach field ramp to field 2
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
        #                      i_start=self.p.i_evap1_current,
        #                      i_end=self.p.i_evap2_current)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.off()
        self.outer_coil.discharge()

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