from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        # self.xvar('frequency_detuned_imaging',np.arange(280.,330.,3)*1.e6)
        # self.xvar('beans',[0,1]*50)

        self.p.beans = 0

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)
        
        # self.xvar('t_tof',np.linspace(10.,500.,2)*1.e-6)
        self.p.t_tof = 20.e-6

        self.p.t_raman_sweep = 1.e-3
        self.p.frequency_raman_sweep_center = 41.1e6
        self.p.frequency_raman_sweep_width = 20.e3
        # self.xvar('frequency_raman_sweep_center', 41.12e6 + np.arange(-400.e3,400.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-5.e5,5.e5,10))
        self.p.frequency_raman_transition = 41.245e6

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.p.amp_raman = 0.35

        # self.xvar('t_raman_pulse',np.linspace(0.,50.e-6,20))
        # self.xvar('t_raman_pulse',[0.,self.p.t_raman_pi_pulse])
        self.p.t_raman_pulse = 24.e-6

        # self.xvar('_t_tweezer_kill',np.linspace(0., 100.e-3,10))
        self.p._t_tweezer_kill = 10.e-3

        # self.p.frequency_detuned_imaging_half = 289.e6 # (self.p.frequency_detuned_imaging_m1 + self.p.frequency_detuned_imaging_0)/2
        # self.xvar('frequency_detuned_imaging_midpoint',np.arange(600.,660,5)*1.e6)
        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        # self.xvar('frequency_detuned_imaging',np.linspace(280.,400,11)*1.e6)
        # self.p.frequency_detuned_imaging = 318.75e6

        self.p.amp_imaging = .25
        # self.xvar('amp_imaging',np.linspace(0.05,.2,10))
        # self.camera_params.amp_imaging = .4
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.gain = 1.

        # self.xvar('t_tweezer_hold',np.linspace(0.1e-3,10.e-3,10))
        self.p.t_tweezer_hold = 7.e-3
        # self.xvar('dimension_slm_mask',np.linspace(0.,200.e-6,10))
        self.p.dimension_slm_mask = 100.e-6
        self.xvar('phase_slm_mask',np.linspace(0.3*np.pi,.7*np.pi,10))
        self.p.phase_slm_mask = .35*np.pi
        # self.xvar('px_slm_phase_mask_position_x',1147 + np.linspace(-10.,10.,5,dtype=int))
        # self.p.px_slm_phase_mask_position_x
        self.p.phase_slm_mask = 2.09
        self.p.t_mot_load = 1.

        self.sampler.gains = np.array([1,0,0,0,0,0,0,0])
        
        self.p.N_repeats = 3

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.sampler.init()
        # self.sampler.set_gain_mu(0,2)
        delay(10.e-3)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)

        self.ttl.line_trigger.wait_for_line_trigger()

        delay(5.7e-3)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.dds.imaging.on()
        delay(5.e-6)
        self.raman.pulse(t=self.p.t_raman_pulse)
        # delay(self.p.t_raman_pulse)
        self.dds.imaging.off()        

        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)
        self.dds.imaging.set_dds(amplitude=.2)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        # delay(self.p.t_tof)

        if self.p.beans:
            delay(10.e-3)
        else:
            delay(self.p.t_tof)

        self.abs_image()

        # print(self.sampler.samples)

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