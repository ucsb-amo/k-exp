from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu
from kexp.util.artiq.async_print import aprint

class hf_monitored_rabi(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        self.p.t_imaging_pulse = 10.e-6
        self.p.N_pulses = 1000

        self.p.amp_imaging = 1.2

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 1

        self.data.apd = self.data.add_data_container(self.p.N_pulses)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        delay(10.e-3)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        for i in range(self.p.N_pulses):
            self.integrator.begin_integrate()
            self.imaging.pulse(self.p.t_imaging_pulse)
            v = self.integrator.stop_and_sample()
            self.integrator.clear()
            self.data.apd.temp_array[i] = v
            delay(15.e-6)

        delay(10.e-3)

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.data.apd.put_data(self.data.apd.temp_array)
        self.core.break_realtime()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        # aprint(self.scope._data)
        self.end(expt_filepath)