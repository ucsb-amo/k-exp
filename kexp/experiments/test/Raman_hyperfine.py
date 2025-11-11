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
        # self.xvar('t_tof',np.linspace(10.,1000.,10)*1.e-6) 


        self.p.t_tof = 300.e-6

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-4.,1.,15))
        self.p.v_hf_tweezer_paint_amp_max = -1.8

        # self.xvar('i_hf_tweezer_load_current',np.linspace(12.5,16.,20))

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.1,.2,15))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .16

        # self.xvar('v_hf_paint_amp_end',np.linspace(-6.5,-4.,15))

        # self.xvar('t_ramp_down_painting_amp',np.linspace(15.e-3,200.e-3,10))

        # self.xvar('t_rf_state_xfer_sweep', np.linspace(15.e-3,150.e-3,10))
        self.p.t_rf_state_xfer_sweep = 50.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1000

        # self.xvar('rf_sweep_width', np.linspace(20.e3,200.e3,10))
        self.p.rf_sweep_width = 160.e3

        # self.xvar('frequency_rf_sweep_state_prep_center', np.arange(146.e6,148.e6,self.p.rf_sweep_width))
        self.p.frequency_rf_sweep_state_prep_center = 147.2e6

        # self.p.t_raman_sweep = 15.e-3
        # self.p.frequency_raman_sweep_center = 147.14e6
        # self.p.frequency_raman_sweep_width = 50.e3
        # self.xvar('frequency_raman_sweep_center', 147.14e6 + np.arange(-150.e3,150.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-5.e5,5.e5,10))
        self.p.frequency_raman_transition = 147.14e6

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.p.amp_raman = 0.35

        # self.xvar('t_raman_pulse',np.linspace(0.,400.e-6,40))
        # self.xvar('t_raman_pulse',[12.e-6,24.e-6])
        # self.p.t_raman_pulse = 12.e-6
        self.p.t_raman_pulse = 23.6e-6
        # self.xvar('t_tweezer_hold',np.linspace(0.,100.,10)*1.e-3)
        self.p.t_tweezer_hold = 55.e-3

        # self.xvar('t_tof',np.linspace(1000.,3000.,10)*1.e-6)

        # self.xvar('hf_imaging_detuning', np.arange(-715.,-690.,3.)*1.e6)
        self.p.hf_imaging_detuning = -565.e6 # 182. -1
        # self.p.hf_imaging_detuning = -704.e6 # 182. -2

        # self.xvar('amp_imaging', np.linspace(.09,.15,15))
        self.p.amp_imaging = .35
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 5
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_load_current)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_hf_tweezers()
        
        # self.rf.sweep(t=self.p.t_rf_state_xfer_sweep, 
        #               frequency_center=self.p.frequency_rf_sweep_state_prep_center,
        #               frequency_sweep_fullwidth=self.p.rf_sweep_width,
        #               n_steps=1000)
        
        # self.rf.set_rf(frequency=self.p.frequency_rf_drive)
        # self.rf.on()
        # delay(self.p.t_rf_drive)
        # self.rf.off()
        # self.init_raman_beams(frequency_transition=self.p.frequency_raman_transition,
        #                       amp_raman=self.p.amp_raman)
        
        # self.raman.pulse(t=self.p.t_raman_pulse)
        # delay(self.p.t_raman_pulse)
       

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=50)

        # delay(self.p.t_raman_pulse)
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
