from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class lz_sweep_transition_find(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        from kamo import Potassium39
        atom = Potassium39()
        b = atom.get_magnetic_field_from_ground_state_transition_frequency(2,-2,1,-1,self.p.frequency_raman_transition)
        f_f1m1_f2m2 = atom.get_ground_state_transition_frequency(2,-2,1,-1,B=b)
        f_f1m1_f10 = atom.get_ground_state_transition_frequency(1,-1,1,0,B=b)
        f_f10_f11 = atom.get_ground_state_transition_frequency(1,0,1,1,B=b)

        df = self.p.frequency_raman_zeeman_state_xfer_sweep_fullwidth

        self.p.frequency_raman_transition = f_f1m1_f10[0]*1.e6
        # self.p.t_raman_pi_pulse_f1m1_f10 = # 
        
        self.xvar('t_raman_pulse',np.linspace(100.,150.,15)*1.e-6)

        self.p.t_tof = 20.e-6
        self.p.N_repeats = 1
        self.camera_params.gain = 300

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.raman.pulse(self.p.t_raman_pulse)

        # self.raman.pulse(self.p.t_raman_pi_pulse_f1m1_f10/2)
        # delay(self.p.t_ramsey)
        # self.raman.pulse(self.p.t_raman_pi_pulse_f1m1_f10/2)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)