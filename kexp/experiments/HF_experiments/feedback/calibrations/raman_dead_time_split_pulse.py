from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
import numpy as np


class raman_dead_time_split_pulse(EnvExperiment, Base):
    """Raman turn-on delay (dead time) from split pulses (2026-10-28).

    A pulse of commanded length t rotates the spin by Omega (t - t0), where t0
    (p.t_raman_pulse_offset in the feedback models) is the pulse area lost at the
    switch: turn-on lag minus any turn-off tail. Splitting a commanded total T
    into N sub-pulses of T/N loses t0 once per sub-pulse:

        theta(N) = N Omega (T/N - t0) = Omega T - N Omega t0

    so the rotation falls by Omega t0 per extra sub-pulse, separately from Omega
    (which the N = 1 point and the references fix). In a pulse-length scan
    (apd_voltage_vs_state_2) t0 only shifts the whole flop, and a fit trades it
    against Omega.

    Each shot runs one configuration (N sub-pulses of tau) from the table built
    in prepare(), indexed by the xvar idx_raman_split_config:

        group 0   N = 0                      no pulse: S_z = +1, the APD 'up' level
        group 1   N = 1, tau = t_pi + t0     the commanded pi pulse: the 'down'
                                             level (second order in a t0 error)
        group 2   T = t_pi/2 + t0, N = 1..4  starts at the equator (steepest S_z)
        group 3   T = 3 t_pi/2 + t0,         the same a half turn later: a second
                  N = 1, 2, 4, 6, 8, 10      t0, ~6 us of drive (decay check)

    t_pi = p.t_raman_pi_pulse (the rate pi time) and t0 = the nominal 127 ns are
    used only to place the totals; the analysis fits its own Omega and t0 from
    the lengths actually run. Each tau is a whole number of RTIO periods
    (p.t_rtio), so the commanded length is exactly what the hardware plays.

    Sub-pulses are p.t_raman_split_gap apart. raman.pulse gates only the switch
    DDS; the two Raman tones run throughout, so the sub-pulses add coherently.
    A two-photon detuning delta turns the spin by delta * gap between them; its
    effect on S_z is second order (1 - cos), negligible for kHz detunings and a
    1 us gap. A sub-pulse shorter than p.t_raman_sub_pulse_min is refused: near
    the switch's rise time the lost area need not be a constant.

    Readout as in apd_voltage_vs_state_2: N_pulses integrated dispersive APD reads
    (data.apd). data.raman_split holds each shot's [N, tau (s), group] as run.
    No scope trace (no photon number is needed here).

    Analysis:
        from waxa import atomdata
        from waxa.analysis.rabi import fit_split_pulse_dead_time
        ad = atomdata(run_id, roi_id='auto', lite=False)
        fit = fit_split_pulse_dead_time(ad.data.raman_split[:, 0], ad.data.raman_split[:, 1],
                                        ad.data.apd, group=ad.data.raman_split[:, 2],
                                        t_pi_ref=ad.p.t_raman_pi_pulse,
                                        t_dead_ref=ad.p.t_raman_pulse_offset,
                                        run_ids=(ad.run_info.run_id,))
        print(fit.summary()); fit.plot()
    """

    def prepare(self):
        Base.__init__(self, camera_select=cameras.apd,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      warmup_shots=3)

        self.p.amp_imaging = 0.2
        self.p.t_pci_pulse = 5.e-6
        self.p.t_between_pulses_mu = 25000  # from read start to next read start, in mu

        self.p.t_raman_pulse_offset = 127.e-9  # nominal t0: places the totals only, not used in the fit
        self.p.t_raman_split_gap = 1.e-6
        self.p.t_raman_sub_pulse_min = 0.5e-6

        t_pi = self.p.t_raman_pi_pulse
        t0 = self.p.t_raman_pulse_offset
        # (group, N, commanded total)
        configs = [(0, 0, 0.), (1, 1, t_pi + t0)]
        configs += [(2, n, 0.5 * t_pi + t0) for n in [1, 2, 3, 4]]
        configs += [(3, n, 1.5 * t_pi + t0) for n in [1, 2, 4, 6, 8, 10]]

        # tau on the RTIO grid; raman.pulse delays floor(t / ref_period), so it gets
        # half a machine unit extra to play exactly tau_mu (t_raman_sub_pulse_cmd)
        ref_period = self.core.ref_period
        grid_mu = int(round(self.p.t_rtio / ref_period))
        group, n_split, tau = [], [], []
        for g, n, total in configs:
            tau_mu = grid_mu * int(round(total / max(n, 1) / ref_period / grid_mu))
            if n > 0 and tau_mu * ref_period < self.p.t_raman_sub_pulse_min:
                raise ValueError(f"group {g}, N = {n}: sub-pulse {tau_mu * ref_period * 1e9:.0f} ns is shorter "
                                 f"than t_raman_sub_pulse_min ({self.p.t_raman_sub_pulse_min * 1e9:.0f} ns)")
            group.append(g)
            n_split.append(n)
            tau.append(tau_mu * ref_period if n > 0 else 0.)
        # float arrays (the kernel writer passes arrays as float). Their length is the
        # number of configs; the shuffled axis is N_repeats times longer, so the saved
        # params do not mistake them for xvar-length lists (needs N_repeats >= 2).
        self.p.raman_split_group_table = np.array(group, dtype=float)
        self.p.N_raman_split_table = np.array(n_split, dtype=float)
        self.p.t_raman_sub_pulse_table = np.array(tau, dtype=float)

        self.p.N_raman_split = 0
        self.p.t_raman_sub_pulse = 0.
        self.p.t_raman_sub_pulse_cmd = 0.
        self.p.raman_split_group = 0

        self.p.idx_raman_split_config = 0
        self.xvar('idx_raman_split_config', np.arange(len(configs)))

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.N_repeats = 8
        if self.p.N_repeats < 2:
            raise ValueError("N_repeats must be >= 2 (the config tables would match the shuffled axis length)")

        self.p.N_pulses = 5

        self.data.apd = self.data.add_data_container(self.p.N_pulses)
        self.data.raman_split = self.data.add_data_container(3)

        self.finish_prepare()

    def compute_new_derived(self):
        idx = self.p.idx_raman_split_config
        if np.ndim(idx) > 0:
            # end of run: the xvar holds its whole array; data.raman_split is the per-shot record
            return
        i = int(idx)
        self.p.raman_split_group = int(self.p.raman_split_group_table[i])
        self.p.N_raman_split = int(self.p.N_raman_split_table[i])
        self.p.t_raman_sub_pulse = float(self.p.t_raman_sub_pulse_table[i])
        self.p.t_raman_sub_pulse_cmd = self.p.t_raman_sub_pulse + 0.5 * self.core.ref_period

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # SLM phase-dot mask written every shot (as apd_voltage_vs_state_2)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.warmup_imaging()
        self.prep_raman()

        for i in range(self.p.N_raman_split):
            self.raman.pulse(self.p.t_raman_sub_pulse_cmd)
            delay(self.p.t_raman_split_gap)

        self.data.raman_split.put_data(float(self.p.N_raman_split), 0)
        self.data.raman_split.put_data(self.p.t_raman_sub_pulse, 1)
        self.data.raman_split.put_data(float(self.p.raman_split_group), 2)

        delay(10.e-6)

        t = now_mu()
        for i in range(self.p.N_pulses):
            self.integrated_imaging_pulse(self.data.apd, t=self.p.t_pci_pulse, idx=i)
            t += self.p.t_between_pulses_mu
            at_mu(t)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
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
