from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
from waxx.control.beat_lock import FREQUENCY_GS_HFS
import numpy as np


class apd_red_detuned_damage_cam(EnvExperiment, Base):
    """Atom number after the red-detuned APD reads, measured on the Andor (2026-10-30).

    Companion to apd_red_detuned_readout (run 90241), which measured the APD
    response but no atom number. Each shot here makes the same reads, then
    images the atoms that are left:

        dispersive spot mask (p.phase_slm_mask), scanned detuning, scanned power
        N_reads APD reads of the atoms          -> data.apd_atoms (as 90241)
        spot mask rewritten to phase 0, imaging back to f1m1 / p.amp_imaging
        hold t_relock_hold (SLM write + beat lock re-lock)
        Andor in-trap absorption image          -> ad.od, ad.atom_number

    The image recipe is the one of align_apd_w_absorption / tweezer_dump_apd
    (f1m1, amp 0.2, 20 us, SLM phase 0, Andor + pickoff stage in the APD path,
    override_apd_stage=True).

    amp_imaging_read = 0 is the control arm: same timeline, same detuning
    jumps, the reads made with the light off (dark=True). Atom number vs
    detuning in that arm tests whether the 150 ms is enough for the beat lock
    to return to f1m1 (it should be flat), and gives the N the other arms are
    compared to. The hold at 182 A costs atoms in every arm alike.

    Not measured here: the no-atom APD level (use 90241: same settings, flat
    in detuning). The Andor image has the 20 us f1m1 pulse of its own, so N is
    the in-trap absorption N, not a count of what the reads left unperturbed
    (heated atoms still absorb).
    """

    def prepare(self):
        Base.__init__(self, camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION,
                      diagnostic_images=False,
                      warmup_shots=3,
                      mot_preload=True,
                      override_apd_stage=True)

        # imaging of the remaining atoms (the tweezer_dump_apd recipe)
        self.p.t_imaging_pulse = 20.e-6
        self.p.amp_imaging = 0.2
        self.p.t_tof = 20.e-6

        # the reads (as 90241)
        self.p.t_pci_pulse = 5.e-6
        self.p.t_between_pulses_mu = 25000
        self.p.N_reads = 5
        self.p.t_relock_hold = 150.e-3          # beat lock back to f1m1 + SLM write

        f_line = self.p.frequency_detuned_hf_f1m1
        df_from_line = np.array([self.p.frequency_detuned_hf_midpoint - f_line,  # present readout
                                 -50.e6, -100.e6, -250.e6, -500.e6, -750.e6, -1000.e6])
        frequencies = f_line + df_from_line
        self.check_beatlock_reachable(frequencies)

        self.p.frequency_detuned_apd_scan = f_line
        self.p.amp_imaging_read = 0.
        self.xvar('frequency_detuned_apd_scan', frequencies)
        self.xvar('amp_imaging_read', np.array([0., 0.2, 0.8, 1.6]))
        self.p.N_repeats = 5

        self.data.apd_atoms = self.data.add_data_container(self.p.N_reads)

        self.finish_prepare(shuffle=True)

    def check_beatlock_reachable(self, frequencies):
        """As apd_red_detuned_readout: refuse a scan the beat lock reference
        cannot produce, before a run id is used."""
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
    def read_block(self, container, dark):
        t = now_mu()
        for i in range(self.p.N_reads):
            self.integrated_imaging_pulse(container, t=self.p.t_pci_pulse, idx=i, dark=dark)
            t += self.p.t_between_pulses_mu
            at_mu(t)

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        amp = self.p.amp_imaging_read
        dark = amp <= 0.
        if dark:
            amp = self.p.amp_imaging

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_apd_scan)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,
                                         dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(amp)

        self.prepare_hf_tweezers(ramp_down_painting=False)
        delay(1.e-3)

        self.read_block(self.data.apd_atoms, dark)

        # the APD read leaves ~0 slack (tweezer_dump_apd, run 90237)
        self.core.break_realtime()
        delay(1.e-3)

        # back to the imaging recipe for the remaining atoms
        self.slm.write_phase_mask_kernel(phase=0.)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)
        delay(self.p.t_relock_hold)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        try:
            self.scan()
        except:
            self.core.break_realtime()
            self.tweezer.off()
            raise

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
