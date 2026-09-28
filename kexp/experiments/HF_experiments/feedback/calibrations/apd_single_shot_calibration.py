from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
import numpy as np


class apd_single_shot_calibration(EnvExperiment, Base):
    """APD up / down / midpoint voltages from ONE shot (2026-09-27).

    The same preparation, imaging and read timing as apd_voltage_vs_state_2
    (the Rabi-flop APD-state calibration), but instead of scanning the Raman
    pulse across shots, every shot reads three known states in turn:

        N_ref_reads reads, atoms as prepared (S_z = +1)           -> data.apd_up
        pi pulse, N_ref_reads reads (S_z = -1)                     -> data.apd_down
        pi/2 pulse from down, N_ref_reads reads (S_z = 0, equator) -> data.apd_mid

    Order: the reads at the poles are made on S_z eigenstates and leave the
    spin alone, so up and down come first. A read at the equator does not:
    the imaging light shift (~50 kHz over 5 us, about a quarter turn) rotates
    the transverse spin, so a pulse AFTER a midpoint read would not reach a
    pole. The midpoint block is therefore last.

    The pi/2 pulse corrects for the turn-on delay t0 = p.t_raman_pulse_offset:
    t_raman_pi_pulse = t0 + 1/(2 f) is a commanded length, so a quarter turn
    is t0 + (t_raman_pi_pulse - t0)/2.

    The drive sits at p.frequency_raman_transition (prep_raman default), so
    the down and midpoint states are only as good as that resonance and the
    pi-time calibration; the analysis reports the down-state residual.
    Tweezers unsqueezed (prepare_hf_tweezers default), as the feedback runs.
    """

    def prepare(self):
        Base.__init__(self, camera_select=cameras.apd,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      warmup_shots=10)

        self.p.amp_imaging = 0.2
        self.p.t_pci_pulse = 5.e-6
        self.p.t_between_pulses_mu = 25000  # from read start to next read start, in mu

        self.p.t_raman_pulse_offset = 127.e-9  # turn-on delay (the lab's dead time)
        self.p.t_raman_half_pi_pulse = self.p.t_raman_pulse_offset \
            + 0.5 * (self.p.t_raman_pi_pulse - self.p.t_raman_pulse_offset)

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6

        self.p.N_ref_reads = 5
        self.p.dummy = 0
        self.xvar('dummy', [0])
        self.p.N_repeats = 20

        self.data.apd_up = self.data.add_data_container(self.p.N_ref_reads)
        self.data.apd_down = self.data.add_data_container(self.p.N_ref_reads)
        self.data.apd_mid = self.data.add_data_container(self.p.N_ref_reads)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare()

    @kernel
    def read_block(self, container):
        t = now_mu()
        for i in range(self.p.N_ref_reads):
            self.integrated_imaging_pulse(container, t=self.p.t_pci_pulse, idx=i)
            t += self.p.t_between_pulses_mu
            at_mu(t)

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.warmup_imaging()
        self.prep_raman()

        delay(10.e-6)

        t = now_mu()
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        at_mu(t)

        # up: the atoms as prepared
        self.read_block(self.data.apd_up)
        delay(10.e-6)

        # down: one pi pulse
        self.raman.pulse(self.p.t_raman_pi_pulse)
        delay(10.e-6)
        self.read_block(self.data.apd_down)
        delay(10.e-6)

        # midpoint: pi/2 from down to the equator; last (reads here disturb the spin)
        self.raman.pulse(self.p.t_raman_half_pi_pulse)
        delay(10.e-6)
        self.read_block(self.data.apd_mid)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
