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
                      imaging_type=img_types.DISPERSIVE)

        # self.xvar('beans',[0]*50)

        # self.p.t_raman_sweep = 1.e-3
        # self.p.frequency_raman_sweep_center = 147.265e6
        # self.p.frequency_raman_sweep_width = 10.e3
        # self.xvar('frequency_raman_sweep_center', 147.2505e6 + np.arange(-3.e3,3.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',119.4637e6 + np.linspace(-2.e3,2.e3,10))
        # self.p.frequency_raman_transition = 147.2592e6 # 182. A -1 -2
        self.p.frequency_raman_transition = 119.4637e6 # 182 A -1 0

        # self.xvar('t_ramsey', np.linspace(0.e-6, 500.e-6, 5))
 
        # self.xvar('t_raman_pulse', np.linspace(0., 300., 110)*1.e-6)
        # self.p.t_raman_pulse = 7.69e-06 / 2 # -1 --> -2
        self.p.t_raman_pulse = 9.0352e-06 / 2 # -1 --> 0
        # self.p.t_raman_pulse = 200.e-6

        # self.xvar('fraction_power_raman',np.linspace(0., 0.5, 10))
        self.p.fraction_power_raman = 0.99
        
        # self.xvar('amp_imaging',np.linspace(0.1,.8,10))
        self.p.amp_imaging = .5

        # self.xvar('hf_imaging_detuning',np.concatenate((np.arange(-578.e6,-564.e6,1.e6),np.arange(-467.e6,-453.e6,1.e6))))
        self.p.hf_imaging_detuning =  -568.e6 # 182. with PID
        # self.p.hf_imaging_detuning =  -538.e6 # 175. with PID

        self.xvar('switch_axis',[0,1])

        self.p.t_img_pulse = 50.e-6

        # self.xvar('relative_phase',np.linspace(0.,np.pi / 2, 5))
        self.p.relative_phase = 0.

        self.p.hf_imaging_detuning_mid = -514.e6 # -1 --> 0

        # self.xvar('dimension_slm_mask',np.linspace(15.e-6,250.e-6,10))
        self.p.dimension_slm_mask = 20.e-6

        # self.p.phase_slm_mask = 0.371 * np.pi
        self.p.phase_slm_mask = 0.186 * np.pi

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,300.e-3,10))
        self.p.t_tweezer_hold = .01e-3

        # self.xvar('t_tof',np.linspace(10.,250.,15)*1.e-6) 
        self.p.t_tof = 90.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 100

        # self.camera_params.gain = 75.

        self.data.apd = self.data.add_data_container(1)
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=self.p.i_hf_raman)
        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning_mid)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)

        self.raman.init(frequency_transition = self.p.frequency_raman_transition, 
                        fraction_power = self.params.fraction_power_raman)
        
        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        self.raman.pulse(self.p.t_raman_pulse)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.imaging.on()
        delay(10.e-6)
        self.imaging.off()
        
        # self.raman.set_phase(relative_phase=self.p.relative_phase)
        delay(10.e-6)

        if self.p.switch_axis:
            self.raman.pulse(self.p.t_raman_pulse)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)