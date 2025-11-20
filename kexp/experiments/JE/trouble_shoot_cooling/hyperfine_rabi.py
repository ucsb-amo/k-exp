from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.p.t_tof = 4250.e-6
        self.p.t_tof = 100.e-6
        # self.xvar('t_tof',np.linspace(10.,400.,10)*1.e-6) 

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.,194.5,15))

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-2.,6.,15))

        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.5,194.5,8))
        # self.xvar('i_hf_tweezer_evap2_current',np.linspace(192.5,194.5,8))

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.07,.3,15))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .12

        # self.xvar('t_rf_state_xfer_sweep',np.linspace(15.e-3, 80.e-3, 8))
        self.p.t_rf_state_xfer_sweep = 35.e-3

        # self.xvar('rf_sweep_width',np.linspace(50.e3, 300.e3, 15))
        self.p.rf_sweep_width = 30.e3

        self.p.frequency_rf_sweep_state_prep_center = 147.14e6
        # self.xvar('frequency_rf_sweep_state_prep_center',147.14e6 + np.arange(-3*self.p.rf_sweep_width, 3*self.p.rf_sweep_width, self.p.rf_sweep_width))

        # self.xvar('frequency_rf_drive',147.18e6 + np.linspace(-20.e3,20.e3,10))
        self.p.frequency_rf_drive = 147.14e6

        # self.xvar('t_rf_drive',np.linspace(0.,20.e-3,40))
        self.p.t_rf_drive = 1.e-3

        # self.xvar('t_tweezer_hold',np.linspace(0.,100.,20)*1.e-3)
        self.p.t_tweezer_hold = 0.01e-3

        # self.xvar('t_tof',np.linspace(1000.,3000.,10)*1.e-6)

        self.xvar('hf_imaging_detuning', np.arange(-1000.,-100.,15.)*1.e6)
        self.p.hf_imaging_detuning = -565.e6 # 182. -1
        # self.p.hf_imaging_detuning = -710.e6 # 182. -2

        # self.xvar('amp_imaging', np.linspace(.09,.15,15))
        self.p.amp_imaging = .35
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_load_current)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_hf_tweezers()
        
        self.rf.sweep(t=self.p.t_rf_state_xfer_sweep, 
                      frequency_center=self.p.frequency_rf_sweep_state_prep_center,
                      frequency_sweep_fullwidth=self.p.rf_sweep_width,
                      n_steps=50)
        
        # self.rf.set_rf(frequency=self.p.frequency_rf_drive)
        # self.rf.on()
        # delay(self.p.t_rf_drive)
        # self.rf.off()

        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.stop_pid()

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
