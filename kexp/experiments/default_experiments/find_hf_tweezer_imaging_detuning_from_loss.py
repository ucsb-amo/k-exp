
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
        
        self.p.t_tweezer_hold = 50.e-3

        self.p.t_tof = 800.e-6
        
        self.p.N_repeats = 3

        self.p.t_mot_load = 1.0
        self.p.t_imaging_pulse = 20.e-6

        self.f_f1m1 = self.p.frequency_detuned_hf_f1m1
        self.f_f0 = -455.e6 # guess based on midpoint

        f_scan_width = 25.e6
        df = 1.e6

        self.fshw = f_scan_width / 2
        f_scan_window = np.arange(-self.fshw, self.fshw+df, df)

        f_scan_array = np.r_[
                    self.f_f1m1 + f_scan_window,
                    self.f_f0 + f_scan_window
                    ]

        self.p.t_in_trap_imaging = 3.e-6
        self.xvar('frequency_detuned_in_trap_imaging',
                  f_scan_array)

        self.data.t_raman_pulse = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        t_raman_pulse = -1.
        if abs(self.p.frequency_detuned_in_trap_imaging - self.f_f1m1) <= self.fshw:
            t_raman_pulse = 0.
            print('imaged state: mF = 1')
        elif abs(self.p.frequency_detuned_in_trap_imaging - self.f_f0) <= self.fshw:
            t_raman_pulse = self.p.t_raman_pi_pulse
            print('imaged state: mF = 0')
        else:
            raise ValueError('scanned detuning is bad somehow')

        t_delay = self.p.t_raman_pi_pulse - t_raman_pulse
        self.data.t_raman_pulse.put_data(t_raman_pulse)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_in_trap_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        # rotate to the other spin state if we are looking for that one
        self.raman.pulse(t_raman_pulse)
        delay(t_delay)

        self.imaging.pulse(self.p.t_in_trap_imaging)

        # rotate rotate back if we rotated the first time
        self.raman.pulse(t_raman_pulse)
        delay(t_delay)
         
        self.set_imaging_detuning(self.p.frequency_detuned_hf_f1m1)
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        # self.abs_image(
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

