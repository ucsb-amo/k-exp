from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from waxx.control.beat_lock import BeatLockImaging
from kexp.base.cameras import img_config

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.configure_imaging_system(imaging_configuration=img_config.SWITCH)

        self.xvar('wee',[0,1]*1)

        self.p.t_tof = 100.e-6
        # self.xvar('t_tof',np.linspace(1000.,4500.,10)*1.e-6)

        # self.xvar('t_pulse',np.linspace(0.,1.,5)*1.e-3)
        self.p.t_pulse = 1.e-6
        # self.p.t_pulse = 

        # self.xvar('dumy',[0]*3)

        self.p.t_tweezer_hold = 10.e-3

        self.p.amp_imaging = .4

        # self.p.hf_imaging_detuning = -617.e6 # 193.2
        self.p.imaging_state = 2.

        self.p.N_repeats = 3
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
    
        self.dds.imaging_x_switch.off()
        
        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_load_current)



        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)


        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)


        # lightsheet evap 1
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
                          paint=True,keep_trap_frequency_constant=False)
                          
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown2_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        self.lightsheet.off()
        self.imaging.set_power(.5)
        self.ttl.imaging_shutter_x.off()
        
        if self.p.wee == 0:
            self.ttl.imaging_shutter_xy.on()
            delay(3.e-3)
            self.imaging.on()
            delay(1.e-3)
            self.imaging.off()
            self.ttl.imaging_shutter_xy.off()
            delay(self.p.t_tweezer_hold)
        
        elif self.p.wee == 1:
            delay(self.p.t_tweezer_hold)
        

        # self.init_raman_beams_nf(frequency_transition=self.p.frequency_raman_transition_nf_1m1_20 - 10.e6,
        #                          fraction_power=1.0)
        # delay(1.e-3)
        # self.raman_nf.pulse(self.p.t_raman_pulse)
        # self.ry_405.pulse(self.p.t_pulse)
        # delay(1.e-3)


        self.imaging.set_power(.3)

        self.ttl.imaging_shutter_x.on()
        
        delay(3.e-3)

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
