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
                      save_data=False,
                      imaging_type=img_types.DISPERSIVE)
        
        self.p.t_imaging_pulse = 20.e-6
        self.xvar('dummy',[0]*1000)
        
        self.p.amp_imaging = 0.5

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 1

        self.camera_params.gain = 100

        self.data.apd = self.data.add_data_container(3)
        # self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        delay(10.e-3)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.integrated_imaging_pulse(self.data.apd, self.p.t_imaging_pulse, 0)

        delay(10.e-6)

        self.raman.pulse(self.p.t_raman_pi_pulse)

        self.integrated_imaging_pulse(self.data.apd, self.p.t_imaging_pulse, 1)

        delay(10.e-6)

        self.tweezer.off()
        delay(600.e-6)

        self.integrated_imaging_pulse(self.data.apd, self.p.t_imaging_pulse, 2)

        delay(self.p.t_tof)

        delay(100.e-3)

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        # self.scope.read_sweep([0])
        self.core.break_realtime()
        delay(100.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        # aprint(self.scope._data)
        self.end(expt_filepath)