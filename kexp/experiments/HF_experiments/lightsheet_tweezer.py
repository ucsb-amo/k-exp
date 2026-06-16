
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras, aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2, tweezer_vpd2_to_vpd1

class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.xvar('v_pd_lightsheet_rampdown3_end', np.linspace(0.,0.86,2))

        # self.xvar('t_tof',np.linspace(100.,1000.,3)*1.e-6)
        self.p.t_tof = 20.e-6
        self.p.t_tweezer_hold = 100.e-3

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)
        self.prepare_hf_tweezers(squeeze=False)
        
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.abs_image()

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

    @kernel
    def prepare_hf_tweezers(self,
                            hybrid_mot=False,
                            squeeze=True,
                            cubic_ramp_squeeze=True,
                            do_tweezer_evap_2=True,
                            do_tweezer_evap_3=True):
        """prepares hf evap tweezers at i_outer = ExptParams.i_non_inter with
        PID enabled.
        """   
        self.switch_d2_2d(1)
        if hybrid_mot == True:
            self.hybrid_mot(self.p.t_mot_load)
        else:
            self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # delay(200.e-3)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        self.set_shims(0.,0.,0.) 

        self.ttl.pd_scope_trig.pulse(1.e-6)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_end=self.p.i_hf_tweezer_load_current)
        
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
                          
        # lightsheet ramp down (to off)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)
        # self.lightsheet.pid_int_zero_ttl.on()
        if self.p.v_pd_lightsheet_rampdown3_end == 0.:
            self.lightsheet.off()

        self.outer_coil.ramp_supply(t=5.e-3,
                             i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            #  i_start=self.p.i_hf_tweezer_evap1_current,
                                i_end=self.p.i_hf_tweezer_evap2_current)
        
        if do_tweezer_evap_2:
        
            self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                            v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                            v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                            paint=True,keep_trap_frequency_constant=True)
            
            if do_tweezer_evap_3:
            
                self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown3,
                                v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown2_end),
                                v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                                paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=10.e-3,
                             i_end=self.p.i_hf_raman)

        # delay(100.e-3)
        # self.outer_coil.ttl_blanking.off()
        # delay(100.e-3)
        
        self.outer_coil.start_pid()
        
        delay(30.e-3)

        if squeeze and do_tweezer_evap_2 and do_tweezer_evap_3:
            self.tweezer_squeeze(cubic_ramp_squeeze)