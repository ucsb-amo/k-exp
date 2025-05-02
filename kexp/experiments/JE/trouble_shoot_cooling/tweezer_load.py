from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 15.e-6
        # self.xvar('t_tof',np.linspace(100,900.,10)*1.e-6)
        # self.xvar('dumy',[0]*500)
        
        self.p.t_lightsheet_hold = .2

        # self.p.t_magtrap = .5

        # self.xvar('t_feshbach_field_rampup',np.linspace(.07,.5,10))

        self.xvar('i_evap2_current',np.linspace(180.,200.,14))
        self.p.i_evap2_current = 180.

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(.3,9.,8))
        self.p.v_pd_tweezer_1064_ramp_end = 5.

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-7.,6.,20))
        self.p.v_tweezer_paint_amp_max = -2.3

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.05,.9,10))
        # self.p.t_tweezer_1064_ramp = 13.e-3

        # self.xvar('t_tweezer_hold',np.linspace(.5,50.,10)*1.e-3)
        self.p.t_tweezer_hold = 1.e-6

        self.p.frequency_tweezer_list = [74.e6,76.e6]
        # self.p.frequency_tweezer_list = np.linspace(76.e6,78.e6,6)

        # a_list = [.45,.55]
        a_list = [.45,.45]
        self.p.amp_tweezer_list = a_list

        # self.xvar('hf_imaging_detuning', np.arange(-620.,-595.,3.)*1.e6)

        # self.xvar('t_imaging_pulse',np.linspace(10.,500.,10)*1.e-6)
        # self.p.t_imaging_pulse = 20.e-6    
        
        # self.camera_params.exposure_time = 500.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.
        self.xvar('hf_imaging_detuning', np.arange(-560.,-490.,5.)*1.e6)
        self.p.hf_imaging_detuning = -560.e6

        # self.xvar('amp_imaging', np.linspace(.03,.2,20))
        self.p.amp_imaging = .35
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = .5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.camera_params.exposure_time = self.params.t_imaging_pulse
        # self.set_high_field_imaging(i_outer=self.p.i_evap2_current)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap2_current)
        
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)

        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        self.outer_coil.off()

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
