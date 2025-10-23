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

        # self.xvar('beans',[0,1]*50)

        self.camera_params.exposure_time = 10.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.p.beans = 0
        
        # self.xvar('t_tof',np.linspace(800.,2500.,15)*1.e-6)
        self.p.t_tof = 1.e-6

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-5.e5,5.e5,10))
        self.p.frequency_raman_transition = 41.2e6

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.p.amp_raman = 0.35

        # self.xvar('t_raman_pulse',np.linspace(0.,25.e-6,20))
        # self.xvar('t_raman_pulse',[17.e-6,0.])
        self.p.t_raman_pulse = 100.e-6

        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.09,.3,10))

        # self.xvar('_t_tweezer_kill',np.linspace(0., 100.e-3,10))
        # self.p._t_tweezer_kill = 10.e-3
        
        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        self.p.t_tweezer_hold = 20.e-3

        self.p.amp_imaging = .08
        # self.xvar('amp_imaging',np.linspace(0.1,.5,10))

        # self.xvar('frequency_detuned_imaging',np.arange(320.,420.,5)*1.e6)
        self.p.frequency_detuned_imaging = 368.e6

        # self.p.frequency_ao_imaging = 375.e6

        self.p.frequency_detuned_imaging_midpoint = 307.e6
        
        # self.xvar('dimension_slm_mask',np.linspace(1.e-6,200.e-6,10))
        self.p.dimension_slm_mask = 25.e-6
        self.xvar('phase_slm_mask',np.linspace(0.,2*np.pi,20))
        # self.p.phase_slm_mask = 1.8 * np.pi
        self.p.phase_slm_mask = np.pi / 2
        self.p.t_mot_load = 1.

        # self.sampler.gains = np.array([1,0,0,0,0,0,0,0])
        
        self.p.N_repeats = 10

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD')

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.sampler.init()
        # self.sampler.set_gain_mu(0,2)
        delay(10.e-3)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)
        # self.init_raman_beams()
        self.ttl.line_trigger.wait_for_line_trigger()

        delay(5.7e-3)

        self.dds.imaging.on()
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.raman.pulse(t=self.p.t_raman_pulse)
        self.dds.imaging.off()   

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(self.p.t_tof)     

        self.abs_image()

        delay(1.e-3)

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(3)
        self.core.break_realtime()

        delay(1.e-3)

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