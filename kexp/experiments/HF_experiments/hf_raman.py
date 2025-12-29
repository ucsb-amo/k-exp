from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('beans',[0,1]*50)
        # self.xvar('t_tof',np.linspace(100.,1500.,10)*1.e-6) 
        self.p.t_raman_sweep = 1.e-3
        self.p.frequency_raman_sweep_center = 147.18e6
        self.p.frequency_raman_sweep_width = 10.e3
        # self.xvar('frequency_raman_sweep_center', 147.25e6 + np.arange(-50.e3,50.e3,self.p.frequency_raman_sweep_width))

        self.p.frequency_raman_transition = 147.25e6 # 147.18e6

        self.xvar('t_raman_pulse',np.linspace(0.,200.e-6,100))
        self.p.t_raman_pulse = 7.707e-6/2

        self.params.fraction_power_raman = 0.2
        
        # self.xvar('amp_imaging',np.linspace(0.15,.4,10))
        # self.p.amp_imaging = .28
        self.p.amp_imaging = .3

        # self.xvar('hf_imaging_detuning',np.linspace(-580.5e6,-300.5e6,50))
        self.p.hf_imaging_detuning = -565.e6 #-635.e6 # -572.e6 #-565.e6 # 182. -1
        
        # self.xvar('dimension_slm_mask',np.linspace(10.e-6, 200.e-6, 8))
        # self.p.dimension_slm_mask = 50.e-6
        # self.xvar('phase_slm_mask',np.linspace(0., 1.7*np.pi, 8))
        self.p.phase_slm_mask = .49 * np.pi
        self.p.dimension_slm_mask = 10.e-6
        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 1.e-3

        self.p.t_tof = 133.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_hf_tweezers()


        self.init_raman_beams(frequency_transition = self.p.frequency_raman_transition, 
                              fraction_power = self.params.fraction_power_raman)

        self.ttl.line_trigger.wait_for_line_trigger()
        delay(5.7e-3)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=100)

        self.raman.pulse(self.p.t_raman_pulse)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.outer_coil.stop_pid()

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