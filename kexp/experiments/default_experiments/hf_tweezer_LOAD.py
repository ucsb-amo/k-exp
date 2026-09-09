from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras, Adjust
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        # Adjust.__init__(self)
        
        # self.p.do_cubic_tweezer_ramp = 1
        # self.xvar('do_cubic_tweezer_ramp',[0,1])

        self.p.t_tof = 600.e-6
        

        # self.xvar('t_pulse',np.linspace(0.,1.,5)*1.e-3)
        self.p.t_pulse = 1.e-6
        # self.p.t_pulse = 

        # self.xvar('dumy',[0]*3)

        self.p.t_tweezer_hold = 20.e-3

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(193.5,197.,6))
        # self.p.i_hf_lightsheet_evap1_current = 195.0
        # self.p.t_hf_lightsheet_rampdown = 0.025
        # self.p.v_pd_hf_lightsheet_rampdown_end = 0.9
        # self.p.i_magtrap_init = 95.
        # self.p.i_hf_tweezer_load_current = 193.
        # self.p.v_hf_tweezer_paint_amp_max = -2.0
        # self.p.t_lightsheet_rampdown3 = 62.e-3

        # self.xvar('i_magtrap_init',np.linspace(32.5,160.,11))

        # self.p.amp_imaging = .2

        # self.p.hf_imaging_detuning = -617.e6 # 193.2
        self.p.imaging_state = 2.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end', np.linspace(0.6,1.5,9))
        # self.p.v_pd_hf_lightsheet_rampdown_end = 2.
        # self.p.v_pd_hf_lightsheet_rampdown_end = 1.

        # self.xvar('t_tof',np.linspace(600.,1400.,6)*1.e-6)

        self.xvar('do_exponential_ramp',[0,1])

        # self.xvar('t_hf_lightsheet_rampdown', np.linspace(25.e-3, 1100.e-3, 4))
        # self.p.t_hf_lightsheet_rampdown = 0.35
        # self.xvar('t_hf_tweezer_1064_ramp', np.linspace(5.e-3, 50.e-3, 5))

        # self.xvar('i_hf_tweezer_load_current',np.linspace(192.,195.,7))

        # self.xvar('v_hf_tweezer_paint_amp_max', np.linspace(-2.5, 0., 9))

        # self.adjust('v_hf_tweezer_paint_amp_max',-5.,5.)
        # self.adjust('t_tweezer_hold',0.,20.e-3,5.e-3)

        # self.xvar('t_lightsheet_rampdown3',np.linspace(0.,175.,11)*1.e-3)
        

        self.p.N_repeats = 3
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_load_current)
        self.imaging.set_power(self.camera_params.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        
        self.gm(self.p.t_gm)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        self.set_shims(0.,0.,0.)
        
        # lightsheet evap 1
        if self.p.do_exponential_ramp:
            self.p.t_hf_lightsheet_rampdown = 0.35
            self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                                v_start=self.p.v_pd_lightsheet_rampup_end,
                                v_end=self.p.v_pd_hf_lightsheet_rampdown_end,
                                tau=self.p.t_hf_lightsheet_rampdown/3)
        else:
            self.p.t_hf_lightsheet_rampdown = 1.1
            self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                                            v_start=self.p.v_pd_lightsheet_rampup_end,
                                            v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_lightsheet_evap1_current,
                             i_end=self.p.i_hf_tweezer_load_current)
    
        self.tweezer.on()
            
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                            v_start=0.,
                            v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                            paint=True,keep_trap_frequency_constant=False,
                            cubic_ramp=False)
                          
        # lightsheet ramp down (to off)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        if self.p.t_lightsheet_rampdown3 > 10.e-3:
            self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                    # v_start=self.p.v_pd_hf_lightsheet_rampdown2_end,
                                    v_end=0.)
            
        self.lightsheet.off()

        # self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
        #                     v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
        #                     v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
        #                     paint=True,keep_trap_frequency_constant=False,
        #                     cubic_ramp=False)
        

        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
        #                     #  i_start=self.p.i_hf_tweezer_evap1_current,
        #                         i_end=self.p.i_hf_tweezer_evap2_current)
        
        
        # self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
        #                 v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
        #                 v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
        #                 paint=True,keep_trap_frequency_constant=True)

        # self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown3,
        #                     v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown2_end),
        #                     v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
        #                     paint=True,keep_trap_frequency_constant=True,low_power=True)


        delay(self.p.t_tweezer_hold)

        # self.init_raman_beams_nf(frequency_transition=self.p.frequency_raman_transition_nf_1m1_20 - 10.e6,
        #                          fraction_power=1.0)
        # delay(1.e-3)
        # self.raman_nf.pulse(self.p.t_raman_pulse)
        # self.ry_405.pulse(self.p.t_pulse)
        # delay(1.e-3)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
