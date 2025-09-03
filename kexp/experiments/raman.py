from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        # self.xvar('frequency_detuned_imaging_m1',np.arange(250.,320.,3)*1.e6)
        # self.xvar('beans',[0]*500)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)
        
        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 600.e-6

        self.p.t_raman_sweep = 1.e-3
        # self.p.frequency_raman_sweep_center = 41.1e6
        self.p.frequency_raman_sweep_width = 10.e3
        # self.xvar('frequency_raman_sweep_center', 41.14e6 + np.arange(-40.e3,40.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-5.e5,5.e5,10))
        self.p.frequency_raman_transition = 41.144e6

        # self.xvar('amp_raman',np.linspace(0.15,.35,5))
        self.p.amp_raman = 0.35
        # self.xvar('frequency_detuned_imaging_m1',318.e6 + np.linspace(-20.e6,20.e6,11))
        self.xvar('t_raman_pulse',np.linspace(0.,50.,20)*1.e-6)
        self.p.t_raman_pulse = 600.e-6

        # self.p.frequency_detuned_imaging_half = 289.e6 # (self.p.frequency_detuned_imaging_m1 + self.p.frequency_detuned_imaging_0)/2
        # self.xvar('frequency_detuned_imaging_midpoint',np.arange(600.,660,5)*1.e6)
        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)

        # self.xvar('amp_imaging',np.linspace(0.1,.5,10)*1.e-6)
        # self.camera_params.amp_imaging = .3
        self.camera_params.exposure_time = 15.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time
        

        self.p.t_tweezer_hold = .01e-3
        # self.xvar('phase_slm_mask',np.linspace(0.,np.pi,10))
        # self.p.phase_slm_mask = 1.4
        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)        
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_lf_tweezers()

        

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)

        self.ttl.line_trigger.wait_for_line_trigger()

        delay(5.7e-3)

        # self.ttl.pd_scope_trig.pulse(1.e-6)

        self.raman.pulse(t=self.p.t_raman_pulse)
        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=100)

        # delay(self.p.t_raman_pulse)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)