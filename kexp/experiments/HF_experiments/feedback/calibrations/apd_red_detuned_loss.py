from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
from waxx.control.beat_lock import FREQUENCY_GS_HFS
import numpy as np


class apd_red_detuned_loss(EnvExperiment, Base):
    """Measurement-induced loss in the red-detuned APD readout (2026-10-30).

    Follow-up to apd_red_detuned_readout (run 90241), whose 5 reads x 5
    repeats could not resolve a decline of the signal at large detuning. Here:
    a train of N_reads=20 reads per shot (atoms, then without atoms, then one
    dark), longer reads, higher power, the largest red detuning the beat lock
    reference allows, and many repeats.

    The loss is read from the APD alone: signal_k = apd_atoms[k] - apd_empty[k]
    against the read index k. A decline of signal_k with k is the proxy; the
    no-atom train (apd_empty vs k) is the control for anything that is not
    the atoms (integrator or light drift along the train). The proxy does not
    separate lost atoms from heated or optically pumped ones, and there is no
    camera to count atoms after the train.

    Scan: frequency_detuned_apd_scan (relative to p.frequency_detuned_hf_f1m1)
    x amp_imaging (PID setpoint, V) x t_pci_pulse (read length). Reads start
    t_pci_pulse + t_read_gap apart (gap 20 us after the pulse; the integrator
    needs >= ~4 us to settle and >= 10 us for clear carry-over). The
    +48.5 MHz point is today's readout (frequency_detuned_hf_midpoint).

    SLM spot at p.phase_slm_mask / p.dimension_slm_mask, as 90241.
    """

    def prepare(self):
        Base.__init__(self, camera_select=cameras.apd,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      warmup_shots=3)

        self.p.t_read_gap = 20.e-6              # end of one pulse to the start of the next
        self.p.t_atoms_gone = 8.e-3             # tweezer off -> no-atom reads (phase_spot)
        self.p.N_reads = 20

        f_line = self.p.frequency_detuned_hf_f1m1
        df_from_line = np.array([self.p.frequency_detuned_hf_midpoint - f_line,  # present readout
                                 -100.e6, -250.e6, -500.e6, -1000.e6, -1500.e6])
        frequencies = f_line + df_from_line
        self.check_beatlock_reachable(frequencies)

        self.p.frequency_detuned_apd_scan = f_line
        self.p.t_pci_pulse = 5.e-6
        self.xvar('frequency_detuned_apd_scan', frequencies)
        self.xvar('amp_imaging', np.array([0.5, 1.0, 2.0]))
        self.xvar('t_pci_pulse', np.array([5.e-6, 20.e-6]))
        self.p.N_repeats = 16

        self.data.apd_atoms = self.data.add_data_container(self.p.N_reads)
        self.data.apd_empty = self.data.add_data_container(self.p.N_reads)
        self.data.apd_dark = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    def check_beatlock_reachable(self, frequencies):
        """Refuse a scan the beat lock reference cannot produce, before a run id
        is used (arithmetic of BeatLockImaging.imaging_detuning_to_beat_ref; the
        400 MHz ceiling is the ARTIQ DDS limit, the lock's own limit is not in
        the code)."""
        im = self.imaging
        f_offset = (1. / im._beat_sign) * (frequencies - im.get_ao_shift() - FREQUENCY_GS_HFS / 2)
        f_ref = f_offset / im._N_beatref_mult
        print(f"[beat lock] offsets {f_offset.min()/1e6:.1f} .. {f_offset.max()/1e6:.1f} MHz, "
              f"reference {f_ref.min()/1e6:.1f} .. {f_ref.max()/1e6:.1f} MHz")
        if f_offset.min() < im._frequency_minimum_beat:
            raise ValueError("scan goes below the beat lock minimum offset")
        if f_ref.min() < 0. or f_ref.max() > 400.e6:
            raise ValueError("scan needs a beat lock reference outside 0..400 MHz")

    @kernel
    def read_block(self, container):
        step = self.core.seconds_to_mu(self.p.t_pci_pulse + self.p.t_read_gap)
        t = now_mu()
        for i in range(self.p.N_reads):
            self.integrated_imaging_pulse(container, t=self.p.t_pci_pulse, idx=i)
            t += step
            at_mu(t)

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_apd_scan)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,
                                         dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        delay(1.e-3)

        self.read_block(self.data.apd_atoms)
        delay(10.e-6)

        self.tweezer.off()
        delay(self.p.t_atoms_gone)

        self.read_block(self.data.apd_empty)
        delay(10.e-6)
        self.integrated_imaging_pulse(self.data.apd_dark, t=self.p.t_pci_pulse, idx=0, dark=True)

        delay(10.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
