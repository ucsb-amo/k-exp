"""FeedbackExptGrid -- FeedbackExptAlt with the hypothesis grid set from the pulse period
(session copy 2026-10-07 23:xx, DESIGN_grid_rule.md; repo base untouched).

Rule: q = grid_step_Hz * T_ref = n + frac. frac = p.feedback_grid_alias_frac (0.4), n =
p.feedback_grid_alias_order (-1 = the integer that keeps the step nearest the legacy 0.25 Omega).
T_ref = the longest gap class of the schedule (p.feedback_grid_alias_T_ref: "long" | "short" |
"mean"), computed from the slack / pulse / imaging / FIFO terms exactly as the kernel does plus the
cycle's extra delays. The grid half-width p.feedback_guess_span_Omega is then DERIVED:
step_Omega = (q / T_ref) / f_Rabi, span = step_Omega * (m - 1) / 2, and written before
Feedback.__init__ builds the grid, so the kernel, the saved params and the replay see an ordinary
span. p.feedback_grid_q, _q_classes, _step_hz, _T_ref_s, _n are recorded.

Remesh: maybe_remesh is overridden so a requested (halved) span is snapped to the nearest
n' + frac before re-gridding; the centre and the clamp are the original code's.

Run files call self.grid_step_Omega() before xvar() to place the initial offsets on grid points.
"""
import numpy as np
from numpy import int64

from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from base_expt_feedback_alt import FeedbackExptAlt


class FeedbackExptGrid(FeedbackExptAlt):

    # ---- host side --------------------------------------------------------------------------
    def _gap_classes_s(self):
        """Distinct inter-pulse periods (s) of the schedule at the nominal pulse time."""
        p = self.p
        base = int(self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=p.t_calculation_slack_compensation_mu,
            t_raman_pulse=p.t_raman_pulse, t_img_pulse=p.t_img_pulse,
            t_raman_pretrigger=p.t_raman_set_pretrigger_mu, t_fifo_mu=p.t_fifo_mu))
        cycle = np.atleast_1d(np.asarray(getattr(p, "t_gap_cycle_extra_us", [0.]), dtype=float))
        extras = sorted(set((np.rint(cycle * 1.e3).astype(np.int64) & ~np.int64(7)).tolist()))
        return [(base + e) * 1.e-9 for e in extras]

    def grid_rule(self):
        p = self.p
        frac = float(getattr(p, "feedback_grid_alias_frac", 0.4))
        order = int(getattr(p, "feedback_grid_alias_order", -1))
        mode = str(getattr(p, "feedback_grid_alias_T_ref", "long"))
        m = int(p.feedback_grid_size)
        classes = self._gap_classes_s()
        T_ref = {"long": max(classes), "short": min(classes), "mean": float(np.mean(classes))}[mode]
        f_rabi = 1.0 / (2.0 * float(p.t_raman_pi_pulse))
        if order < 0:
            order = max(0, int(round(0.25 * f_rabi * T_ref - frac)))
        q = order + frac
        step_hz = q / T_ref
        step_Om = step_hz / f_rabi
        span = step_Om * (m - 1) / 2.0
        q_classes = [step_hz * T for T in classes]
        return dict(frac=frac, order=order, mode=mode, m=m, classes_s=classes, T_ref_s=T_ref, f_rabi=f_rabi,
                    q=q, step_hz=step_hz, step_Omega=step_Om, span_Omega=span, q_classes=q_classes)

    def grid_step_Omega(self):
        return float(self.grid_rule()["step_Omega"])

    def finish_prepare(self, shuffle=True):
        p = self.p
        g = self.grid_rule()
        p.feedback_grid_alias_frac = float(g["frac"])
        p.feedback_grid_alias_order = int(g["order"])
        p.feedback_grid_alias_T_ref = g["mode"]
        p.feedback_guess_span_Omega = float(g["span_Omega"])          # derived; what the kernel reads
        p.feedback_grid_q = float(g["q"])
        p.feedback_grid_q_classes = np.asarray(g["q_classes"], dtype=float)
        p.feedback_grid_step_hz = float(g["step_hz"])
        p.feedback_grid_T_ref_s = float(g["T_ref_s"])
        p.feedback_grid_T_classes_s = np.asarray(g["classes_s"], dtype=float)
        # kernel-side copies for the remesh snap (plain floats)
        self.t_alias_ref_s = float(g["T_ref_s"])
        self.grid_alias_frac = float(g["frac"])
        print(f"grid rule: m {g['m']}, frac {g['frac']}, n {g['order']} -> q {g['q']:.3f} on T_ref {g['T_ref_s']*1e6:.2f} us "
              f"({g['mode']}); step {g['step_hz']/1e3:.3f} kHz = {g['step_Omega']:.4f} Omega; span +/-{g['span_Omega']:.3f} Omega "
              f"(f_Rabi {g['f_rabi']/1e3:.2f} kHz)")
        for T, qc in zip(g["classes_s"], g["q_classes"]):
            d = [abs(k * qc - round(k * qc)) for k in range(1, 6)]
            flag = "  <-- WARNING: neighbour within 0.1 of a tooth" if min(d[:4]) < 0.1 else ""
            print(f"  gap {T*1e6:6.2f} us: q {qc:.3f}; k=1..5 distance to a tooth " + " ".join(f"{x:.2f}" for x in d) + flag)
        super().finish_prepare(shuffle=shuffle)

    # ---- kernel side ------------------------------------------------------------------------
    @portable(flags={"fast-math"})
    def maybe_remesh(self, posterior_std, omega_center):
        """Feedback.maybe_remesh with the requested span snapped to the alias rule
        (q' = n' + frac on T_ref) before re-gridding."""
        if self.feedback_remesh_threshold_omega > 0.0:
            if posterior_std < (self.feedback_remesh_threshold_omega):
                self._remesh_counter += 1
            elif posterior_std > self.p.remesh_reset_counter_threshold_fraction * self.feedback_remesh_threshold_omega:
                self._remesh_counter = 0

            if self._remesh_counter > (self.p.remesh_after_n_good_shots-1):
                self.feedback_remesh_threshold_omega *= self.p.remesh_threshold_scale_factor
                span_req = self.feedback_remesh_span_Omega * self.p.remesh_scale_factor
                f_rabi = self.Omega / (2.0 * np.pi)
                step_req_hz = 2.0 * span_req * f_rabi / (self.m - 1)
                q_req = step_req_hz * self.t_alias_ref_s
                n_new = int(q_req - self.grid_alias_frac + 0.5)
                if n_new < 0:
                    n_new = 0
                q_new = n_new + self.grid_alias_frac
                span_new = (q_new / self.t_alias_ref_s) / f_rabi * (self.m - 1) * 0.5
                self.feedback_remesh_span_Omega = span_new
                interpolate_posterior = self.p.remesh_interpolate_posterior
                interpolate_states = self.p.remesh_interpolate_states
                expand_clipped = self.p.remesh_expand_clipped_grid_to_requested_size
                self.remesh_to_centered(omega_center, span_new,
                                        interpolate_posterior, interpolate_states,
                                        expand_clipped)
