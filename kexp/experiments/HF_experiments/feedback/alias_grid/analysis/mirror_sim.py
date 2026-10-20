"""SYNTHETIC ONLY: pulse-steering policies for the feedback loop, on the as-written model.

    python policy_sim.py <run_id> [n_seeds]

Takes one run's calibration, offsets and 21-pt production grid (FeedbackReplay(ad)), and
closes the loop with the model as written (Feedback.generate_posterior for the controller on the
21-pt grid; the true spin stepped with the same Bloch rotation, imaging-light-shift z rotation and
back-action damping as simulate_feedback_run_apd; photon noise = stored std_n). A second posterior
on a 401-pt grid scores every shot (fine-grid MAP / mass near resonance). Each policy chooses, per
pulse, the drive frequency (always the controller's MAP, as production), the drive PHASE (the axis
azimuth in the MAP hypothesis frame) and the pulse DURATION:

  current      phase-continuous DDS (no phase choice), durations random 0.5-1 t_pi  (production)
  current_pi2  phase-continuous, all pulses pi/2                                    (control)
  maxslope     pulse 0: pi/2 at azimuth 0; then pi/2 about the axis PARALLEL to the MAP state's
               transverse direction -> predicted s_z unchanged (0), measured s_z = L sin(eps)
  pole_reset   alternate: return-to-pole rotation from the MAP state (axis/angle as the kernel's
               re_initalize_spin_vector, sign verified below), then pi/2 at azimuth 0
  hybrid3      cycle of 3: pi/2 at azimuth 0 (from the pole), pi/2 parallel to the MAP state
               (informative), return-to-pole
  maxslope_pole  maxslope, but every 4th pulse is a return-to-pole
  current_par    production random durations, axis azimuth parallel to the MAP transverse state
  current_perp   production random durations, axis azimuth 90 deg from the MAP transverse state

Metrics per policy (n_seeds x 105 shots, truth on the nominal resonance): 21-pt hit, fine MAP
within +/-0.04 Omega, fine mass within +/-0.04 Omega, median |fine MAP| in kHz, mean posterior
std of the 401-pt posterior (kHz), and the mean Bloch-vector length at the last pulse.
Gaps: the run's standard gap formula (slack as recorded) + pulse duration. Design calculation;
nothing written back.
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HALF_WIN = 0.04
POLICIES = ["current", "hold2", "hold3", "mean2"]
HOLD = {"current": 1, "hold2": 2, "hold3": 3, "mean2": 1}


def rotate(s, phi, delta_omega, Omega, dt_ideal):
    """One pulse on Bloch vector s, exactly as generate_posterior steps a hypothesis:
    axis (Omega cos phi, Omega sin phi, delta_omega)/H, angle -dt_ideal*H."""
    sx, sy, sz = s
    H = np.sqrt(Omega * Omega + delta_omega * delta_omega)
    if H > 0:
        ux, uy, uz = Omega / H * np.cos(phi), Omega / H * np.sin(phi), delta_omega / H
        th = -dt_ideal * H
        c, sn = np.cos(th), np.sin(th)
    else:
        ux = uy = uz = 0.0; c, sn = 1.0, 0.0
    omc = 1 - c
    hx = (c + omc*ux*ux)*sx + (omc*ux*uy - sn*uz)*sy + (omc*ux*uz + sn*uy)*sz
    hy = (omc*ux*uy + sn*uz)*sx + (c + omc*uy*uy)*sy + (omc*uy*uz - sn*ux)*sz
    hz = (omc*ux*uz - sn*uy)*sx + (omc*uy*uz + sn*ux)*sy + (c + omc*uz*uz)*sz
    return np.array([hx, hy, hz])


def return_to_pole(s, Omega, sign):
    """Axis azimuth and ideal duration that map s to +z under `rotate` (resonant drive).
    sign = +1 uses the kernel's re_initalize_spin_vector convention (theta = atan2(-sx, sy),
    phi = atan2(|s_perp|, sz)); sign = -1 the opposite axis. Verified numerically in main()."""
    sx, sy, sz = s
    xy = np.hypot(sx, sy)
    theta = np.arctan2(-sx, sy)
    phi = np.arctan2(xy, sz)
    if sign < 0:
        theta += np.pi
    return theta, phi / Omega


def main(rid, n_seeds=5):
    from kexp import atomdata
    from kexp.analysis import FeedbackReplay

    ad = atomdata(rid, roi_id='auto', lite=False)
    ctl = FeedbackReplay(ad)                      # 21-pt controller
    sc = FeedbackReplay(ad); sc.p.feedback_grid_size = 20 * (int(ctl.m) - 1) + 1; sc._reinitialize_feedback()
    Omega = float(ctl.Omega); f_Om = Omega / (2 * np.pi)
    omega_res = float(ctl._omega_resonance_rad_s)
    t_off = float(ctl.p.t_raman_pulse_offset)
    t_pi = float(ctl.p.t_raman_pi_pulse)
    t_img = float(ctl.p.t_img_pulse)
    n_ph = float(ctl.N_photons_per_shot); sig = float(ctl.std_n_photons_per_shot)
    v_down, v_range = float(ctl.v_apd_all_down), float(ctl.v_range)
    C = float(ctl.back_action_coherence); w_ls = float(ctl.omega_z_lightshift)
    base_gap = float(ctl._t_between_base_mu) * 1e-9
    t_rr = np.asarray(ad.data.t_raman_pulse, float).reshape(-1, int(ad.p.N_pulses))
    n_shot, n_step = t_rr.shape
    offs = ctl._resolve_fractional_initial_offset_r(n_repeat=n_shot)
    T_pre = float(ctl.p.t_io_update_pretrigger_mu) * 1e-9

    # verify the return-to-pole convention against `rotate`
    rng0 = np.random.default_rng(0)
    best = None
    for sign in (+1, -1):
        err = 0.0
        for _ in range(50):
            v = rng0.normal(size=3); v /= np.linalg.norm(v)
            th, dt = return_to_pole(v, Omega, sign)
            out = rotate(v, th, 0.0, Omega, dt)
            err = max(err, abs(out[2] - 1.0))
        print(f"return_to_pole sign {sign:+d}: max |s_z - 1| after rotation = {err:.2e}")
        if best is None or err < best[1]:
            best = (sign, err)
    POLE_SIGN = best[0]
    print(f"using sign {POLE_SIGN:+d} (kernel convention is +1)")

    def choose(policy, i, s_map):
        """-> (azimuth in the MAP frame, ideal duration) for pulse i; None azimuth = phase-continuous."""
        if policy in ("current", "hold2", "hold3", "mean2"):
            return None, t_rr[0, i]  # placeholder, replaced per shot
        if policy in ("current_par", "current_perp"):
            # random durations as production, but the axis azimuth chosen from the MAP state:
            # parallel to its transverse direction (par) or 90 deg from it (perp)
            az0 = np.arctan2(s_map[1], s_map[0]) if i > 0 else 0.0
            return (az0 if policy == "current_par" else az0 + 0.5 * np.pi), t_rr[0, i]
        if policy == "current_pi2":
            return None, 0.5 * t_pi
        az_map = np.arctan2(s_map[1], s_map[0])
        if policy == "maxslope":
            return (0.0 if i == 0 else az_map), 0.5 * t_pi
        if policy == "pole_reset":
            if i % 2 == 0:
                return 0.0, 0.5 * t_pi
            th, dt = return_to_pole(s_map, Omega, POLE_SIGN); return th, dt
        if policy == "hybrid3":
            k = i % 3
            if k == 0:
                return 0.0, 0.5 * t_pi
            if k == 1:
                return az_map, 0.5 * t_pi
            th, dt = return_to_pole(s_map, Omega, POLE_SIGN); return th, dt
        if policy == "maxslope_pole":
            if i % 4 == 3:
                th, dt = return_to_pole(s_map, Omega, POLE_SIGN); return th, dt
            return (0.0 if i == 0 else az_map), 0.5 * t_pi
        raise ValueError(policy)

    results = {}
    for policy in POLICIES:
        hit, near, mres, mapkhz, pstd, length = [], [], [], [], [], []
        hit_sign = []
        for seed in range(n_seeds):
            rng = np.random.default_rng(1000 + seed)
            for r in range(n_shot):
                for F in (ctl, sc):
                    g, z = F._grid_for_offset(float(offs[r])); F.omega_guess_list = g; F.omega_sq_list = g * g; F.reset_feedback_state()
                z_ctl = int(np.argmin(np.abs(ctl.omega_guess_list - omega_res)))
                det_sc = (sc.omega_guess_list - omega_res) / Omega
                s_true = np.array([0.0, 0.0, 1.0])
                omega_ctrl = omega_res + Omega * float(offs[r])
                ctl.omega_raman = omega_ctrl; sc.omega_raman = omega_ctrl
                phase_tracker = 0.0; omega_prev = 0.0; t = 0.0
                for i in range(n_step):
                    # MAP state in the controller's own frame
                    j = int(np.argmax(ctl.P0)) if i > 0 else z_ctl
                    omega_map = float(ctl.omega_guess_list[j]) if i > 0 else omega_ctrl
                    s_map = np.array([ctl.state_x[j], ctl.state_y[j], ctl.state_z[j]])
                    az, dt_ideal = choose(policy, i, s_map)
                    if policy in ("current", "hold2", "hold3", "mean2", "current_par", "current_perp"):
                        dt_ideal = float(t_rr[r, i]) - t_off
                    dt_eff = dt_ideal + t_off
                    if i >= HOLD[policy]:
                        omega_ctrl = omega_map
                    if policy == "mean2" and i == 1:
                        omega_ctrl = float(np.sum(np.asarray(ctl.P0) * np.asarray(ctl.omega_guess_list)))
                    gap_prev = base_gap + (dt_eff_prev if i > 0 else 0.0)
                    if az is None:
                        # phase-continuous DDS model (as _run_shot_into_buffers)
                        if i > 0:
                            phase_tracker += (gap_prev - T_pre) * omega_prev + T_pre * omega_ctrl
                    else:
                        # drive phase so that the axis azimuth in the MAP frame is `az`
                        phase_tracker = az + omega_map * t
                    # truth
                    phi_true = phase_tracker - omega_res * t
                    h = rotate(s_true, phi_true, omega_ctrl - omega_res, Omega, dt_ideal)
                    p1 = float(ctl.expected_photon_fraction(h[2]))
                    k_true = n_ph * p1 + rng.normal(0.0, sig)
                    v = v_down + k_true * v_range / n_ph
                    k_val = float(np.rint(n_ph * (v - v_down) / v_range))
                    a_z = dt_eff * (omega_res - omega_ctrl) - w_ls * t_img
                    cz, sz_ = np.cos(a_z), np.sin(a_z)
                    s_true = np.array([(cz * h[0] + sz_ * h[1]) * C, (-sz_ * h[0] + cz * h[1]) * C, h[2]])
                    # posteriors
                    for F in (ctl, sc):
                        F.omega_raman = omega_ctrl
                        F.t_raman_pulse_current = dt_eff; F.t_raman_pulse_ideal_current = dt_ideal
                        F.generate_posterior(k_val, t, phase_raman_pulse_start=phase_tracker,
                                             update_raman_frequency=1, update_rabi_frequency=0, include_photon_noise=1)
                        F.Omega = Omega
                    omega_prev = omega_ctrl; dt_eff_prev = dt_eff
                    t += base_gap + dt_eff
                # score
                hit.append(float(np.argmax(ctl.P0) == z_ctl)); hit_sign.append(float(np.sign(offs[r])))
                Pf = np.asarray(sc.P0); jm = int(np.argmax(Pf))
                near.append(float(abs(det_sc[jm]) <= HALF_WIN))
                mapkhz.append(abs(det_sc[jm]) * f_Om / 1e3)
                mres.append(float(Pf[np.abs(det_sc) <= HALF_WIN + 1e-9].sum()))
                mu = float(np.sum(Pf * det_sc)); pstd.append(float(np.sqrt(max(np.sum(Pf * det_sc ** 2) - mu * mu, 0.0))) * f_Om / 1e3)
                length.append(float(np.linalg.norm(s_true)))

        def ms(x):
            x = np.asarray(x, float); return float(x.mean()), float(x.std(ddof=1) / np.sqrt(x.size))
        out = dict(n=len(hit))
        for k, v in (("hit21", hit), ("fine_near", near), ("mass_res", mres), ("post_std_kHz", pstd), ("length_last", length)):
            out[k], out[k + "_sem"] = ms(v)
        out["map_abs_kHz_median"] = float(np.median(mapkhz))
        hs = np.asarray(hit_sign); hh = np.asarray(hit)
        out["hit_neg"], out["hit_pos"] = float(hh[hs < 0].mean()), float(hh[hs > 0].mean())
        results[policy] = out
        print(f"{policy:14s} hit_neg {out['hit_neg']:.3f} hit_pos {out['hit_pos']:.3f} | hit21 {out['hit21']:.3f}±{out['hit21_sem']:.3f}  fine_near {out['fine_near']:.3f}±{out['fine_near_sem']:.3f}  "
              f"mass_res {out['mass_res']:.4f}±{out['mass_res_sem']:.4f}  |MAP| med {out['map_abs_kHz_median']:.1f} kHz  "
              f"post std {out['post_std_kHz']:.1f} kHz  L_last {out['length_last']:.2f}", flush=True)

    json.dump(dict(run_id=rid, n_seeds=n_seeds, pole_sign=POLE_SIGN, results=results),
              open(os.path.join(HERE, f"mirror_sim_{rid}.json"), "w"), indent=1)
    names = list(results); x = np.arange(len(names))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    ax[0].errorbar(x, [results[k]["hit21"] for k in names], yerr=[results[k]["hit21_sem"] for k in names], fmt="o", color="#eb6834", capsize=3)
    ax[0].set_ylabel("21-pt hit"); ax[0].set_ylim(0, 0.8)
    ax[1].errorbar(x - 0.1, [results[k]["fine_near"] for k in names], yerr=[results[k]["fine_near_sem"] for k in names], fmt="o", color="#2a78d6", capsize=3, label="fine MAP within ±0.04 Ω")
    ax[1].errorbar(x + 0.1, [2 * results[k]["mass_res"] for k in names], yerr=[2 * results[k]["mass_res_sem"] for k in names], fmt="^", color="#008300", capsize=3, label="2 × mass within ±0.04 Ω")
    ax[1].legend(fontsize=8); ax[1].set_ylabel("fine-grid localization")
    ax[2].errorbar(x, [results[k]["post_std_kHz"] for k in names], yerr=[results[k]["post_std_kHz_sem"] for k in names], fmt="s", color="#4a3aa7", capsize=3, label="401-pt posterior std (kHz)")
    ax[2].plot(x, [results[k]["length_last"] * 50 for k in names], "d", color="#8a8a8a", label="50 × Bloch length at last pulse")
    ax[2].legend(fontsize=8)
    for a in ax:
        a.set_xticks(x); a.set_xticklabels(names, rotation=35, ha="right", fontsize=8); a.grid(alpha=0.2)
    fig.suptitle(f"SYNTHETIC: pulse-steering policies on run {rid}'s calibration (f_Rabi {f_Om/1e3:.1f} kHz, stored noise), {n_seeds} × {n_shot} shots", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig16_mirror.png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
