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
                    camera_select=cameras.andor,imaging_type=img_types.ABSORPTION,
                    save_data=True, warmup_shots=5)

        self.p.v_pd_lf_lightsheet_rampdown_end = 0.85
        # self.xvar('v_pd_lf_lightsheet_rampdown_end',np.linspace(0.4,1.5,8))
        # self.p.v_pd_lf_lightsheet_rampdown_end2 = 0.4
        self.p.i_lf_lightsheet_evap1_current=12.9
        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(12.9,14.6,8))
        self.p.t_lf_lightsheet_rampdown = 0.15
        # self.xvar('t_lf_lightsheet_rampdown',np.linspace(0.05,0.2,6))
        self.p.n_lightsheet_evap1_decay_coeff = 1.25


        
    

        self.p.t_lf_tweezer_1064_rampdown = 0.6
        self.p.i_lf_tweezer_load_current=12.8 #5s wait


        # self.xvar('i_lf_tweezer_load_current',np.linspace(11.8,13.6,8))

        self.p.i_lf_tweezer_evap1_current = 12.15 #5s wait 
        # self.p.i_lf_tweezer_evap1_current = 14.35

        # self.xvar('i_lf_tweezer_evap1_current',np.linspace(11.8,13.3,11))

        self.p.offset = 51.e6
        self.xvar('offset',np.linspace(-24.e6,10.e6,15))

        # self.xvar('t_tof',np.linspace(100.,600.,7)*1.e-6)
        self.p.t_tof = 400.e-6

        self.p.t_tweezer_hold = 1.e-3
        self.p.v_pd_hf_tweezer_1064_rampdown_end = 0.16

        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(0.16,3.,8))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 7.5
        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(1.,8.,3))

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-1.,4.,15))
        self.p.v_hf_tweezer_paint_amp_max = 2.0
        self.p.amp_imaging = 0.3
        # self.xvar('amp_imaging',np.linspace(0.1,0.5,5))

        # self.xvar('beans',np.linspace(1,7,7))
        self.p.post_abs_wait = 0.
        # self.xvar()

        self.p.t_mot_load = 1.
        self.p.N_repeats = 3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=low_field_imaging_detuning(self.p.i_lf_tweezer_evap1_current)+self.p.offset)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.switch_d2_2d(1)
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
        # lightsheet evap 1
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        #feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_lf_lightsheet_evap1_current,
                            i_end=self.p.i_lf_tweezer_load_current)


        
        self.tweezer.on()
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                                  v_start=0.,
                                  v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                  paint=True,keep_trap_frequency_constant=False,
                                  tau=-self.p.t_hf_tweezer_1064_ramp/3)
        #lightsheet ramp, to off
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                        v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                        v_end=self.p.v_pd_lightsheet_rampdown3_end)
                
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                                     i_start=self.p.i_lf_tweezer_load_current,
                                     i_end=self.p.i_lf_tweezer_evap1_current)

        # # # # tweezer evap 1 with constant trap frequency
        self.tweezer.exponential_ramp(t=self.p.t_lf_tweezer_1064_rampdown,
                        v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                        v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                        paint=True,keep_trap_frequency_constant=True,v_awg_am_max=self.p.v_hf_tweezer_paint_amp_max)
    
        
        # # # # # # # tweezer evap 2 with constant trap frequency
        # self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
        #                 v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown_end),
        #                 v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
        #                 paint=True,keep_trap_frequency_constant=True,low_power=True)


        # # delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        delay(self.p.t_tof)

        self.abs_image()
        delay(self.p.post_abs_wait)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)