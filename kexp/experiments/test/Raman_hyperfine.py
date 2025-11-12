from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu
from artiq.language import now_mu
T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.DISPERSIVE)
        
        # self.p.t_tof = 4250.e-6
        # self.xvar('t_tof',np.linspace(100.,2000.,10)*1.e-6) 


        self.p.t_tof = 2.e-6

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-4.,1.,15))
        self.p.v_hf_tweezer_paint_amp_max = -1.8

        # self.xvar('i_hf_tweezer_load_current',np.linspace(12.5,16.,20))

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.08,.2,15))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .18

        self.p.t_raman_sweep = 3.e-3
        # self.p.frequency_raman_sweep_center = 147.14e6
        self.p.frequency_raman_sweep_width = 20.e3
        # self.xvar('frequency_raman_sweep_center', 147.2e6 + np.arange(-200.e3,250.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-5.e5,5.e5,10))
        self.p.frequency_raman_transition = 147.18e6 # 147.18e6

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        # self.p.amp_raman = 0.11
        self.params.fraction_power_raman = 1.

        # self.xvar('t_raman_pulse',np.linspace(0,100.e-6,20))
        self.xvar('t_raman_pulse',[0.e-6,26.e-6])
        # self.p.t_raman_pulse = 12.e-6

        # self.xvar('t_tweezer_hold',np.linspace(0.,100.,10)*1.e-3)
        self.p.t_tweezer_hold = .01e-3

        # self.xvar('t_tof',np.linspace(1000.,3000.,10)*1.e-6)
        
        self.p.phase_slm_mask = 1. * np.pi
        self.xvar('phase_slm_mask',np.linspace(0.,2.7*np.pi,15))

        # self.xvar('hf_imaging_detuning', np.arange(-715.,-690.,3.)*1.e6)
        self.p.hf_imaging_detuning = -565.e6 # 182. -1
        # self.p.hf_imaging_detuning = -704.e6 # 182. -2
        self.p.hf_imaging_detuning_mid = -641.e6
        # self.xvar('hf_imaging_detuning_mid',np.arange( -704.*1.e6,-565.*1.e6,7*1.e6))

        # self.xvar('amp_imaging', np.linspace(.1,.54,10))
        self.p.amp_imaging = .39
        # self.p.amp_imaging = .1

        self.camera_params.exposure_time = 20.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.p.imaging_state = 2.
        self.p.t_continuous_rabi = 150.e-6
        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning_mid)
        # self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_load_current)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_hf_tweezers()

        self.init_raman_beams()

        self.ttl.line_trigger.wait_for_line_trigger()

        delay(5.7e-3)
        
        self.raman.pulse(t=self.p.t_raman_pulse)
        # delay(self.p.t_raman_pulse)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=100)

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
