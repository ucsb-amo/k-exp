from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_raman_transition',119.4637e6 + np.linspace(-2.e3,2.e3,10))
        # self.p.frequency_raman_transition = 147.2592e6 # 182. A -1 -2
        # self.p.frequency_raman_transition = 119.4637e6 # 182 A -1 0

        self.p.frequency_raman_offset = 10.e3

        self.xvar('t_ramsey', np.linspace(0.e-6, 100.e-6, 10))
        self.p.t_ramsey = 10.e-6

        # self.xvar('relative_phase',np.linspace(0.,np.pi, 11))
 
        # self.xvar('t_raman_pulse', np.linspace(0., 300., 110)*1.e-6)
        # self.p.t_raman_pulse = 9.0352e-06 / 2 # -1 --> 0
        
        # self.xvar('amp_imaging',np.linspace(0.1,.8,10))
        self.p.amp_imaging = .5

        # self.xvar('hf_imaging_detuning',np.concatenate((np.arange(-578.e6,-564.e6,1.e6),np.arange(-467.e6,-453.e6,1.e6))))
        # self.p.hf_imaging_detuning =  -568.e6 # 182. with PID
        # self.p.hf_imaging_detuning =  -538.e6 # 175. with PID

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,300.e-3,10))
        self.p.t_tweezer_hold = .01e-3

        # self.xvar('t_tof',np.linspace(10.,250.,15)*1.e-6) 
        self.p.t_tof = 90.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 1

        # self.camera_params.gain = 75.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=self.p.i_hf_raman)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)

        self.raman.init(frequency_transition = self.p.frequency_raman_transition, 
                        fraction_power = self.params.fraction_power_raman,
                        phase_mode = 0)
        
        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        self.raman.pulse(self.p.t_raman_pi_pulse / 2)
        # delay(self.p.t_raman_pulse)

        # t = now_mu()
        self.raman.set(frequency_transition=self.p.frequency_raman_transition + self.p.frequency_raman_offset)
        # tf = now_mu() - t
        delay(self.p.t_ramsey)

        # self.raman.set(relative_phase=self.p.relative_phase,phase_mode = 1)

        self.raman.set(frequency_transition=self.p.frequency_raman_transition)

        self.raman.pulse(self.p.t_raman_pi_pulse / 2)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        # self.outer_coil.stop_pid()

        # self.outer_coil.off()

        # print(tf)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)