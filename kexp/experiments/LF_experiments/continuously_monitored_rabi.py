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
                      imaging_type=img_types.DISPERSIVE)

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.params.fraction_power_raman = 1.
        # self.xvar('t_raman_stateprep_pulse',np.linspace(0.,25.e-6,20))
        # self.xvar('t_raman_stateprep_pulse',[0, 12.2e-6])

        self.p.t_raman_stateprep_pulse = 0.
        self.p.t_continuous_rabi = 150.e-6
        
        # self.xvar('amp_imaging',np.linspace(0.15,.54,10))
        # self.p.amp_imaging = .28
        self.p.amp_imaging = .39
        # self.xvar('frequency_detuned_imaging',np.arange(290.,413.,3)*1.e6)
        self.p.frequency_detuned_imaging = 355.e6
        self.p.frequency_detuned_imaging_midpoint = 308.e6
        
        # self.xvar('dimension_slm_mask',np.linspace(1.e-6,200.e-6,10))
        self.p.dimension_slm_mask = 50.e-6
        # self.xvar('phase_slm_mask',np.linspace(0.,2.7*np.pi,10))
        self.p.phase_slm_mask = 1.7 * np.pi

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 10.e-3
        self.p.t_tof = 133.e-6
        self.p.t_mot_load = 1.

        self.camera_params.exposure_time = 10.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time
        
        self.p.N_repeats = 10

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging)
        # self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(5.7e-3)

        # self.raman.pulse(t=self.p.t_raman_stateprep_pulse)

        self.dds.imaging.on()
        self.raman.on()
        self.ttl.pd_scope_trig.pulse(1.e-6)
        delay(self.p.t_continuous_rabi)
        self.dds.imaging.off()
        self.raman.off()

        # self.imaging.init(frequency_polmod=10.e3,t_phase_origin_mu=now_mu())

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(self.p.t_tof)     

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(20.e-3)

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