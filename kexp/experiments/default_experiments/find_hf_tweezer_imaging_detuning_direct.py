
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.t_tweezer_hold = 10.e-3

        self.p.t_tof = 1000.e-6
        
        self.p.N_repeats = 1

        self.p.t_mot_load = 1.0
        self.p.t_imaging_pulse = 20.e-6

        self.f_f1m1 = self.p.frequency_detuned_hf_f1m1
        self.f_f0 = -457.e6 # guess based on midpoint

        self.p.imaged_state_mF = 0

        f_scan_width = 10.e6
        df = 3.e6

        self.fshw = f_scan_width / 2
        f_scan_window = np.arange(-self.fshw, self.fshw+df, df)

        if self.p.imaged_state_mF:
            f_scan_array = self.f_f1m1 + f_scan_window
        else:
            f_scan_array = self.f_f0 + f_scan_window
                        
        self.xvar('frequency_detuned_imaging', f_scan_array)

        self.data.t_raman_pulse = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        t_raman_pulse = -1.
        if self.p.imaged_state_mF == 1:
            t_raman_pulse = 0.
        elif self.p.imaged_state_mF == 0:
            t_raman_pulse = self.p.t_raman_pi_pulse

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()
        self.raman.pulse(t_raman_pulse)
        
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

