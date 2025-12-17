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

        # self.p.t_raman_sweep = 1.e-3
        # self.p.frequency_raman_sweep_center = 147.18e6
        # self.p.frequency_raman_sweep_width = 10.e3
        # self.xvar('frequency_raman_sweep_center', 147.18e6 + np.arange(-60.e3,60.e3,self.p.frequency_raman_sweep_width))

        self.p.frequency_raman_transition = 147.18e6 # 147.18e6

        # self.xvar('t_raman_pulse',np.linspace(0.,400.e-6,10))
        self.p.t_raman_pulse = 50.e-6

        self.params.fraction_power_raman = .1
        
        # self.xvar('amp_imaging',np.linspace(0.15,.4,10))
        # self.p.amp_imaging = .28
        self.p.amp_imaging = .18

        self.p.hf_imaging_detuning = -565.e6 # 182. -1
        
        # self.xvar('dimension_slm_mask',np.linspace(10.e-6,200.e-6,10))
        # self.p.dimension_slm_mask = 50.e-6
        # self.xvar('phase_slm_mask',znp.linspace(0.,2.7*np.pi,10))
        self.p.phase_slm_mask = .6 * np.pi
        self.p.dimension_slm_mask = 100.e-6

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 1.e-3

        self.p.t_tof = 133.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 20

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_hf_tweezers()

        self.init_raman_beams()

        self.ttl.line_trigger.wait_for_line_trigger()
        delay(5.7e-3)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=50)

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