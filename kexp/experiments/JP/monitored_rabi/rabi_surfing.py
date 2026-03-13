from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class rabi_oscillation(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.p.amp_imaging_pci = 1.

        self.p.t_gate_time = self.p.t_imaging_pulse

        self.p.t_imaging_pulse = 5.e-6
        self.p.t_tof = 100.e-6
        self.p.N_repeats = 1

        self.p.N_pi_pulses = 4
        self.data.apd = self.data.add_data_container(self.p.N_pi_pulses)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.integrator.init()

        # # set up weak measurement
        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.imaging.set_power(self.p.amp_imaging_pci)

        # self.prepare_hf_tweezers()
        # self.prep_raman()
        
        # self.ttl.pd_scope_trig3.pulse(1.e-6)

        # delay(10.e-6)

        # for i in range(self.p.N_pi_pulses):
        
        #     self.integrator.begin_integrate()
        #     self.imaging.pulse(self.p.t_imaging_pulse)
        #     self.data.apd.temp_array[i] = self.integrator.stop_and_sample()
        #     self.integrator.clear()

        #     delay(3.e-6)

        #     self.raman.pulse(self.p.t_raman_pi_pulse)

        #     delay(3.e-6)

        # self.ttl.raman_shutter.off()

        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.imaging.set_power(self.camera_params.amp_imaging)

        # delay(self.p.t_tweezer_hold)

        # self.tweezer.off()

        # delay(self.p.t_tof)
        # self.abs_image()

        # self.core.wait_until_mu(now_mu())
        # self.data.apd.put_data(self.data.apd.temp_array)
        # self.scope.read_sweep([0,2,3])
        # self.core.break_realtime()

        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        if self.p.amp_imaging_pci != 0.:
            self.imaging.set_power(self.p.amp_imaging_pci)
        self.core.break_realtime()

        self.prepare_hf_tweezers()
        # self.prep_raman()

        self.ttl.pd_scope_trig3.pulse(1.e-8)

        # for i in range(self.p.N_pi_pulses):
        #     self.integrator.begin_integrate()
        #     if self.p.amp_imaging_pci != 0.:
        #         self.imaging.pulse(self.p.t_imaging_pulse)
        #     else:
        #         delay(self.p.t_imaging_pulse)
        #     delay(self.p.t_gate_time - self.p.t_imaging_pulse)
        #     # delay(300.e-9)
        #     self.data.apd.temp_array[i] = self.integrator.stop_and_sample()
        #     self.integrator.clear()
        #     delay(1.e-6)

        #     self.raman.pulse(self.p.t_raman_pi_pulse)

        for i in range(self.p.N_pi_pulses):
            self.integrator.ttl_integrate.on()
            self.integrator.ttl_reset.on()
            delay(10.e-6)
            self.integrator.ttl_integrate.off()
            self.integrator.ttl_integrate.off()
            delay(10.e-6)
            self.integrator.ttl_integrate.on()
            self.integrator.ttl_reset.on()
            delay(10.e-6)
            
        delay(10.e-3)

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.data.apd.put_data(self.data.apd.temp_array)
        self.scope.read_sweep([0,2,3])
        self.core.break_realtime()
        delay(30.e-3)

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