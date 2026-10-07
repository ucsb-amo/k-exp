from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from kexp.calibrations import low_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                    camera_select=cameras.xy_basler,
                    save_data=True, warmup_shots=1)


        self.p.v_pd_lf_lightsheet_rampdown_end = 0.85
        # self.xvar('v_pd_lf_lightsheet_rampdown_end',np.linspace(0.4,1.5,8))
        # self.p.v_pd_lf_lightsheet_rampdown_end2 = 0.4
        self.p.i_lf_lightsheet_evap1_current=12.9
        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(12.5,14.6,16))
        self.p.t_lf_lightsheet_rampdown = 0.15
        # self.xvar('t_lf_lightsheet_rampdown',np.linspace(0.05,0.2,6))
        self.p.n_lightsheet_evap1_decay_coeff = 1.25


        self.p.offset = 45.e6
        # self.xvar('offset',np.linspace(-75.e6,154.e6,70))
        self.p.i_lf_tweezer_load_current=14.0


        self.p.t_tof = 396.e-6
        # self.xvar('t_tof',np.linspace(200,2600,7)*1.e-6)
        # self.camera_params.gain = 14.
        # self.adjust('camera_params.gain',0.,15.)
        self.p.t_tweezer_hold = 1.e-3

        self.p.post_abs_wait = 0.

        # self.xvar('beans',np.linspace(1,10,10))
        self.p.t_feshbach_field_rampup = 42.e-3
        # self.xvar('t_feshbach_field_rampup',np.linspace(1.e-3,50.e-3,9))

        self.p.t_mot_load = 1.
        self.p.N_repeats = 3
        # self.p.imaging_state = 2.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_load_current)
        self.set_imaging_detuning(frequency_detuned=low_field_imaging_detuning(self.p.i_lf_lightsheet_evap1_current)+self.p.offset)
        # self.imaging.set_power(self.camera_params.amp_imaging)


        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        delay(self.p.t_lightsheet_hold)

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                            i_start=0.,
                            i_end=self.p.i_lf_lightsheet_evap1_current)
        self.set_shims(0.,0.,0.) 
        self.ttl.pd_scope_trig.pulse(1.e-6)  
        # # # lightsheet evap 1
        self.lightsheet.exponential_ramp(t=self.p.t_lf_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_lf_lightsheet_rampdown_end)

        # # #feshbach field ramp to field 3
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
        #                     i_start=self.p.i_lf_lightsheet_evap1_current,
        #                     i_end=self.p.i_lf_tweezer_load_current)
        # delay(self.p.t_lightsheet_hold)
              
        self.lightsheet.off()

        delay(self.p.t_tof)
        
        self.abs_image()
        delay(self.p.post_abs_wait)
        self.outer_coil.off()
        

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)