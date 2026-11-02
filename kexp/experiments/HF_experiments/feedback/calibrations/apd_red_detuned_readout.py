from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
from waxx.control.beat_lock import FREQUENCY_GS_HFS
import numpy as np


class apd_red_detuned_readout(EnvExperiment, Base):
    """APD response vs imaging detuning, red of the F=1 mF=-1 line (2026-10-30).

    Question: can the dispersive APD readout be done far red of the transition
    out of the prepared state (|1,-1> after evap), where the phase shift falls
    as 1/detuning but the photon scattering (damage) falls as 1/detuning^2?

    Every shot prepares the usual HF tweezer atoms (nothing else: no Raman, no
    warmup_imaging -- its 1 ms pulse at the scanned detuning/power would hit the
    atoms before the first read), then:

        N_reads reads with atoms            -> data.apd_atoms[0..N-1]
        tweezer off, wait for them to leave
        N_reads reads without atoms         -> data.apd_empty[0..N-1]
        one read with no light              -> data.apd_dark

    Signal = apd_atoms - apd_empty at the same detuning and power. The drop
    from read 0 to read N-1 is a damage proxy (atoms lost, heated or optically
    pumped all lower it); it is not a measurement of loss -- take an absorption
    image after the reads for that.

    Scan: frequency_detuned_apd_scan x amp_imaging. Detunings are given
    relative to p.frequency_detuned_hf_f1m1 (the |1,-1> line at 182 A, the
    imaging field). The +48.5 MHz point is the present readout
    (frequency_detuned_hf_midpoint), for comparison in the same run. Power is
    scanned because the signal falls as P/detuning at fixed power: holding the
    signal needs P proportional to detuning.

    The SLM phase spot is left at p.phase_slm_mask / p.dimension_slm_mask.

    Beat lock: set_imaging_detuning is called first in the shot, then the
    seconds-long tweezer preparation runs, so the beat lock has that long to
    settle after a jump of up to ~1.1 GHz (shuffled order). There is no lock
    readback; a lock that did not hold would show as a wrong apd_empty level.
    """

    def prepare(self):
        Base.__init__(self, camera_select=cameras.apd,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      warmup_shots=3)

        self.p.t_pci_pulse = 5.e-6              # as the other APD readouts
        self.p.t_between_pulses_mu = 25000      # read start to next read start, mu
        self.p.t_atoms_gone = 8.e-3             # tweezer off -> no-atom reads (phase_spot)
        self.p.N_reads = 5

        # detuning from the |1,-1> line, Hz. Red is negative.
        f_line = self.p.frequency_detuned_hf_f1m1
        df_from_line = np.array([self.p.frequency_detuned_hf_midpoint - f_line,  # present readout
                                 -25.e6, -50.e6, -100.e6, -200.e6,
                                 -350.e6, -500.e6, -750.e6, -1000.e6])
        frequencies = f_line + df_from_line
        self.check_beatlock_reachable(frequencies)

        self.p.frequency_detuned_apd_scan = f_line
        self.xvar('frequency_detuned_apd_scan', frequencies)
        self.xvar('amp_imaging', np.array([0.2, 0.4, 0.8, 1.6]))
        # self.xvar('phase_slm_mask', np.pi * np.linspace(0.2, 0.5, 7))  # parked: spot phase at one detuning
        self.p.N_repeats = 5

        self.data.apd_atoms = self.data.add_data_container(self.p.N_reads)
        self.data.apd_empty = self.data.add_data_container(self.p.N_reads)
        self.data.apd_dark = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    def check_beatlock_reachable(self, frequencies):
        """Refuse a scan the beat lock reference cannot produce, before a run id
        is used. Same arithmetic as BeatLockImaging.imaging_detuning_to_beat_ref;
        the 400 MHz ceiling is the ARTIQ DDS limit it prints about. The lock's
        own upper limit is not in the code."""
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
        t = now_mu()
        for i in range(self.p.N_reads):
            self.integrated_imaging_pulse(container, t=self.p.t_pci_pulse, idx=i)
            t += self.p.t_between_pulses_mu
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
