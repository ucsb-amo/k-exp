from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class phase_spot(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,camera_select=cameras.apd,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        # self.xvar('amp_imaging',np.linspace(0.1,1.,10))
        self.p.amp_imaging = 0.2
        self.p.t_imaging_pulse = 5.e-6

        # f = 1.e6
        # df = 0.5e6
        # self.xvar('frequency_detuned_hf_midpoint', -519.5e6 + np.arange(-f,f+df,df))

        # self.p.frequency_detuned_hf_midpoint = -5.0e6

        # self.xvar('phase_slm_mask', 0.387097 * np.pi + np.linspace(-0.2, 0.2, 5) * np.pi)
        self.xvar('phase_slm_mask', np.linspace(0.30,1.0,11) * np.pi)
        self.p.phase_slm_mask = 0.387097 * np.pi

        # self.xvar('dimension_slm_mask',np.linspace(15.e-6,250.e-6,10))
        # self.p.dimension_slm_mask = 20.e-6
        
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse
        
        self.p.N_repeats = 3

        # apd slots: 0 = up, 1 = down, 2 = none (dark), 3 = superposition
        self.data.apd = self.data.add_data_container(4)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        # self.p.frequency_detuned_hf_midpoint = -518.50e6

        self.finish_prepare(shuffle=True)

    def up_first(self) -> TBool:
        """Whether this shot should measure the "up" spin state first.

        Alternates deterministically based on the repeat number of the
        current phase_slm_mask value, not the shot order -- so every other
        repeat of a given phase value starts up-first vs down-first,
        regardless of how the scan order was randomized.

        Repeats are laid out along the axis as [v0]*R + [v1]*R + ..., so the
        repeat slot is (canonical index) % R.  With the default random scan
        order (and shuffle=False) xvar.values stay canonical and
        xvar.counter is that index directly; the legacy per-axis scheme
        (shuffle='axis') permutes the values, so the canonical index must be
        recovered through the recorded permutation.
        """
        xvar = self.scan_xvars[0]
        if getattr(self, 'scan_order_scheme', 'axis') == 'axis' and len(xvar.sort_idx):
            canonical_idx = int(xvar.sort_idx[xvar.counter])
        else:
            canonical_idx = int(xvar.counter)
        repeat_idx = canonical_idx % self.p.N_repeats
        return repeat_idx % 2 == 0

    @kernel
    def scan_kernel(self):

        self.integrator.init()

        up_first = self.up_first()

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman(phase_mode=0)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        idx0 = 0
        idx1 = 1
        if not up_first:
            # if do pi pulse first, first spin state is now spin down
            self.raman.pulse(self.p.t_raman_pulse)
            idx0 = 1
            idx1 = 0

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=idx0) # first spin state
        delay(5.e-6)

        self.raman.pulse(self.p.t_raman_pulse)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=idx1) # second spin state
        delay(5.e-6)

        # pi/2 pulse from whichever spin state we ended on -> equal superposition.
        # Done regardless of up_first, so idx=3 is always the superposition.
        self.raman.pulse(self.p.t_raman_pulse/2)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=3) # superposition
        delay(10.e-6)

        self.tweezer.off()

        delay(8.e-3)
        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=2) # dark

        delay(10.e-3)

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