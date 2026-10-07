from kexp.config import ExptParams as expt_params_kexp
import numpy as np
from numpy import int64

class ExptParams(expt_params_kexp):
    def __init__(self):
        super().__init__()

        # run 76036
        # self.frequency_detuned_hf_f1m1 = -574.51e6
        # self.frequency_detuned_hf_f10 = -465.38e6
        # self.frequency_detuned_hf_midpoint = -519.94e6

        self.update_raman_frequency_bool = 0
        self.include_photon_noise = 1

        self.feedback_grid_size = 21
        self.N_pulses = 17
        self.N_repeats = 5

        self.feedback_fractional_initial_offset = 0.0
        # Centre the hypothesis grid on the exact initial offset, so any real
        # offset works (2026-09-27). 0 = the old placement on round(offset);
        # run files without this key were taken with that, and replay honours it.
        self.feedback_grid_center_exact_offset = 1
        # 21 hypotheses at 0.25 Omega: feedback_guess_span_Omega is the grid
        # HALF-width, so the step is 2 * 2.5 / 20.
        self.feedback_guess_span_Omega = 2.5

        # Threshold for adaptive remesh: if posterior std < threshold * Omega,
        # halve the grid span and re-centre on omega_raman.  0.0 = disabled.
        self.feedback_remesh_threshold_Omega = 0.0
        self.remesh_interpolate_posterior = 0
        self.remesh_interpolate_states = 0
        self.remesh_expand_clipped_grid_to_requested_size = 1
        self.remesh_scale_factor = 0.5
        self.remesh_threshold_scale_factor = 0.5
        self.remesh_after_n_good_shots = 1
        self.remesh_reset_counter_threshold_fraction = 1.5
        self.n_initial_shots_before_remesh = 2

        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        # AOM/switch turn-on latency: the programmed pulse is this much longer
        # than the coherent rotation area it actually produces. Only the
        # difference matters, so it stays scalar even when the pulse times
        # themselves are randomized. t_raman_pulse_ideal is derived from it.
        self.t_raman_pulse_offset = 127.e-9
        self.t_raman_pulse_ideal = self.t_raman_pulse - self.t_raman_pulse_offset

        # calibration run 78267
        # img amp 0.2, pulse time 5.0e-06 s
        # self.frequency_lightshift = 4.061e+04  # Hz, +/- 1.5e+03 Hz, imaging amp 0.2 #80654
        # run 83203 | RabiJointPosterior (apd_joint_calibration, f free, t0 127 ns), nuisances verdict PASS
        # self.frequency_lightshift = 5.011e+04  # Hz, +/- 951, at t_img_pulse 5 us, imaging amp 0.2 (mod 1/t_img, up to sign) #83203, 2026-09-27
        # self.frequency_lightshift = 3.697e+04  # Hz, +/- 3.2e+03, absorption Ramsey phase jump (reference phase pi assumed), imaging amp 0.2, t_pulse 5 us #83469, 2026-09-28
        # self.frequency_lightshift = 2.973e+04  # Hz, +/- 7.3e+03, absorption Ramsey phase jump (reference phase pi assumed), imaging amp 0.2, t_pulse 5 us, fringe amp 51 on offset 593 #83760, 2026-09-29
        self.frequency_lightshift = 4.225e+04  # Hz, +/- 1.8e+03, absorption Ramsey phase jump (reference phase pi assumed), imaging amp 0.2, t_pulse 5 us, fringe amp 558 on offset 1247 #84966, 2026-10-02
                
        # calibration run 78309 (S_z endpoints from 'fit', deg-2 S_z response fit)
        self.t_img_pulse = 5e-06  # s
        self.amp_imaging = 0.2
        # self.v_apd_all_up = -0.12361
        # self.v_apd_all_down = -0.19702
        # self.n_photons_per_shot = 1336.2
        # self.std_n_photons_up = 440.27
        # self.std_n_photons_down = 212.75
        # self.std_n_photons_per_shot = 326.51 # avg of up/down
        # self.std_n_photons_per_shot = 212.75 # using down std
        # self.feedback_measurement_midpoint_fraction = 0.4719
        # APD-state calibration runs 83193-83194 (apd_voltage_vs_state_2 variant,
        # phase_slm_mask 2.028 pi), pooled: the two consecutive runs that met the
        # posterior plan's agreement rule (contrast within 15 %, V_up within
        # 2 sigma). python -m kexp.analysis.apd_state_mapping 83193 83194: S_z from
        # the joint flop fit, degree-1 single-shot fit, all 5 pulses.
        # self.v_apd_all_up = -0.15945 #83193-83194, 2026-09-27  # +/- 0.0013 V with run-to-run scatter
        # self.v_apd_all_down = -0.19903 #83193-83194, 2026-09-27  # +/- 0.0010 V
        # self.n_photons_per_shot = 724.05 #83193-83194, 2026-09-27  # scope integral, up minus down per pulse, +/- 33 (SRS gain chain from the notebook, not measured in the run)
        # self.std_n_photons_per_shot = 171.73 #83193-83194, 2026-09-27  # n * sigma_V / v_range = 724.1 * 9.39 mV / 39.59 mV (within-run, down: the larger endpoint noise)
        # self.feedback_measurement_midpoint_fraction = 0.5 #83193-83194, 2026-09-27  # linear map (quadratic term not resolved, p 0.83)
        # Recalibrated 2026-09-27 evening: runs 83201-83202 (same file, 10 warm-up
        # shots), pooled -- the first two runs agreed (contrast 8.4 %, V_up 0.2 sigma).
        # self.v_apd_all_up = -0.15417 #83201-83202, 2026-09-27  # +/- 0.00075 V
        # self.v_apd_all_up = -0.14367 #83217, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83217
        # self.v_apd_all_up = -0.15087 #83227, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83227 --degree 1 (linear fallback, user-approved: curvature resolved, midpoint outside 0.35-0.65)
        # self.v_apd_all_up = -0.15395 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237
        # self.v_apd_all_up = -0.15194 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15624 #83246, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83246 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15397 #83257, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83257 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15721 #83284, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83284 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.16246 #83294, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83294 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.16449 #83304, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83304 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15860 #83314, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83314 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.16085 #83324, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83324 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15881 #83334, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83334 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15668 #83345, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83345 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.16120 #83350, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83350 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.16306 #83357, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83357 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.14928 #83473, 2026-09-28  # procedure step 4 APD calibration, 7 pts x 5, SLM mask written every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.14928 #83473, 2026-09-28  # procedure step 4 re-analysis with t_pi 6.1713e-06 (#83474), SLM mask every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.14526 #83520, 2026-09-28  # contrast re-check after the SLM check + joint 83518 (user-approved write-back), retry after 83519 suspicious, apd_state_mapping 83520 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_up = -0.15210 #83526, 2026-09-28  # hourly recal (feedback procedure, user-approved), rabi_posterior_cli 83526 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.v_apd_all_up = -0.14545 #83640, 2026-09-29  # joint recal accepted after the recovery (rise rule 06:4x, user-approved write-backs), rabi_posterior_cli 83640 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.v_apd_all_up = -0.10472 #83676, 2026-09-29  # +/- 0.0018 V, apd_state_mapping 83676 --sz-source params --degree 1, new integrator window (gate delay 0.7 / extra 1.0 / settle 4.0 us)
        # self.v_apd_all_up = -0.09009 #83888, 2026-09-30  # procedure step 4 after contrast recovery (contrast 44.2 +/- 2.6 mV, pre-registered rule), apd_state_mapping 83888 --sz-source params --degree 1, new integrator window
        # self.v_apd_all_up = -0.08988 #83888, 2026-09-30  # procedure step 5 re-analysis of the step-4 run with t_pi 6.5070e-06 (#83889 joint), apd_mapping_tpi.py 6.507e-6 83888 (apd_state_mapping --sz-source params --degree 1)
        # self.v_apd_all_up = -0.09800 #83927, 2026-09-30  # window-mode recal (pre-registered rule, user fallback cycle), apd_state_mapping 83927 --sz-source params --degree 1
        # self.v_apd_all_up = -0.08155 #84969, 2026-10-02  # step 4 calibration (feedback procedure 2026-10-02; retry agreeing with 84968), apd_state_mapping 84969 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        self.v_apd_all_up = -0.08585 #84975, 2026-10-02  # user-requested retry of the step-4 calibration (feedback procedure 2026-10-02), apd_state_mapping 84975 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.20248 #83201-83202, 2026-09-27  # +/- 0.0017 V with run-to-run scatter
        # self.v_apd_all_down = -0.20441 #83217, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83217
        # self.v_apd_all_down = -0.20229 #83227, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83227 --degree 1 (linear fallback, user-approved: curvature resolved, midpoint outside 0.35-0.65)
        # self.v_apd_all_down = -0.19845 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237
        # self.v_apd_all_down = -0.19651 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19515 #83246, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83246 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19524 #83257, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83257 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19209 #83284, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83284 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.18585 #83294, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83294 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.18806 #83304, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83304 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19024 #83314, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83314 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19009 #83324, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83324 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19223 #83334, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83334 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.19192 #83345, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83345 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.18652 #83350, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83350 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.18928 #83357, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83357 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.17834 #83473, 2026-09-28  # procedure step 4 APD calibration, 7 pts x 5, SLM mask written every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.17831 #83473, 2026-09-28  # procedure step 4 re-analysis with t_pi 6.1713e-06 (#83474), SLM mask every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.17640 #83520, 2026-09-28  # contrast re-check after the SLM check + joint 83518 (user-approved write-back), retry after 83519 suspicious, apd_state_mapping 83520 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.v_apd_all_down = -0.17022 #83526, 2026-09-28  # hourly recal (feedback procedure, user-approved), rabi_posterior_cli 83526 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.v_apd_all_down = -0.17297 #83640, 2026-09-29  # joint recal accepted after the recovery (rise rule 06:4x, user-approved write-backs), rabi_posterior_cli 83640 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.v_apd_all_down = -0.14504 #83676, 2026-09-29  # +/- 0.0019 V, apd_state_mapping 83676 --sz-source params --degree 1, new integrator window (gate delay 0.7 / extra 1.0 / settle 4.0 us)
        # self.v_apd_all_down = -0.13433 #83888, 2026-09-30  # procedure step 4 after contrast recovery (contrast 44.2 +/- 2.6 mV, pre-registered rule), apd_state_mapping 83888 --sz-source params --degree 1, new integrator window
        # self.v_apd_all_down = -0.13362 #83888, 2026-09-30  # procedure step 5 re-analysis of the step-4 run with t_pi 6.5070e-06 (#83889 joint), apd_mapping_tpi.py 6.507e-6 83888 (apd_state_mapping --sz-source params --degree 1)
        # self.v_apd_all_down = -0.12326 #83927, 2026-09-30  # window-mode recal (pre-registered rule, user fallback cycle), apd_state_mapping 83927 --sz-source params --degree 1
        # self.v_apd_all_down = -0.13280 #84969, 2026-10-02  # step 4 calibration (feedback procedure 2026-10-02; retry agreeing with 84968), apd_state_mapping 84969 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        self.v_apd_all_down = -0.13315 #84975, 2026-10-02  # user-requested retry of the step-4 calibration (feedback procedure 2026-10-02), apd_state_mapping 84975 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 851.73 #83201-83202, 2026-09-27  # scope integral, up minus down per pulse, +/- 25 (SRS gain chain from the notebook, not measured in the run)
        # self.n_photons_per_shot = 1119.22 #83217, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83217
        # self.n_photons_per_shot = 910.13 #83227, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83227 --degree 1 (linear fallback, user-approved: curvature resolved, midpoint outside 0.35-0.65)
        # self.n_photons_per_shot = 791.91 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237
        # self.n_photons_per_shot = 793.83 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 731.49 #83246, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83246 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 735.48 #83257, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83257 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 644.80 #83284, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83284 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 421.22 #83294, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83294 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 374.31 #83304, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83304 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 582.18 #83314, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83314 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 548.09 #83324, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83324 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 587.82 #83334, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83334 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 638.95 #83345, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83345 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 500.75 #83350, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83350 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 448.62 #83357, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83357 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 527.11 #83473, 2026-09-28  # procedure step 4 APD calibration, 7 pts x 5, SLM mask written every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 526.79 #83473, 2026-09-28  # procedure step 4 re-analysis with t_pi 6.1713e-06 (#83474), SLM mask every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 600.46 #83520, 2026-09-28  # contrast re-check after the SLM check + joint 83518 (user-approved write-back), retry after 83519 suspicious, apd_state_mapping 83520 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.n_photons_per_shot = 349.46 #83526, 2026-09-28  # hourly recal (feedback procedure, user-approved), rabi_posterior_cli 83526 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.n_photons_per_shot = 530.66 #83640, 2026-09-29  # joint recal accepted after the recovery (rise rule 06:4x, user-approved write-backs), rabi_posterior_cli 83640 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.n_photons_per_shot = 562.39 #83676, 2026-09-29  # +/- 44, scope integral up minus down per pulse, apd_state_mapping 83676 --sz-source params --degree 1, new integrator window (gate delay 0.7 / extra 1.0 / settle 4.0 us)
        # self.n_photons_per_shot = 660.46 #83888, 2026-09-30  # procedure step 4 after contrast recovery (contrast 44.2 +/- 2.6 mV, pre-registered rule), apd_state_mapping 83888 --sz-source params --degree 1, new integrator window
        # self.n_photons_per_shot = 652.25 #83888, 2026-09-30  # procedure step 5 re-analysis of the step-4 run with t_pi 6.5070e-06 (#83889 joint), apd_mapping_tpi.py 6.507e-6 83888 (apd_state_mapping --sz-source params --degree 1)
        # self.n_photons_per_shot = 377.80 #83927, 2026-09-30  # window-mode recal (pre-registered rule, user fallback cycle), apd_state_mapping 83927 --sz-source params --degree 1
        # self.n_photons_per_shot = 736.97 #84969, 2026-10-02  # step 4 calibration (feedback procedure 2026-10-02; retry agreeing with 84968), apd_state_mapping 84969 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        self.n_photons_per_shot = 646.37 #84975, 2026-10-02  # user-requested retry of the step-4 calibration (feedback procedure 2026-10-02), apd_state_mapping 84975 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 150.36 #83201-83202, 2026-09-27  # n * sigma_V / v_range = 851.7 * 8.53 mV / 48.31 mV (within-run, up: the larger endpoint noise)
        # self.std_n_photons_per_shot = 178.11 #83217, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83217
        # self.std_n_photons_per_shot = 183.07 #83227, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83227 --degree 1 (linear fallback, user-approved: curvature resolved, midpoint outside 0.35-0.65)
        # self.std_n_photons_per_shot = 143.24 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237
        # self.std_n_photons_per_shot = 147.34 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 160.68 #83246, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83246 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 129.63 #83257, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83257 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 148.13 #83284, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83284 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 149.78 #83294, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83294 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 150.87 #83304, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83304 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 168.53 #83314, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83314 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 144.52 #83324, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83324 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 166.90 #83334, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83334 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 137.50 #83345, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83345 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 166.25 #83350, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83350 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 155.58 #83357, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83357 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 142.11 #83473, 2026-09-28  # procedure step 4 APD calibration, 7 pts x 5, SLM mask written every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 142.16 #83473, 2026-09-28  # procedure step 4 re-analysis with t_pi 6.1713e-06 (#83474), SLM mask every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 146.21 #83520, 2026-09-28  # contrast re-check after the SLM check + joint 83518 (user-approved write-back), retry after 83519 suspicious, apd_state_mapping 83520 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.std_n_photons_per_shot = 161.66 #83676, 2026-09-29  # 562.4 * 11.59 mV / 40.32 mV (within-run, down), apd_state_mapping 83676 --sz-source params --degree 1, new integrator window (gate delay 0.7 / extra 1.0 / settle 4.0 us)
        # self.std_n_photons_per_shot = 147.31 #83888, 2026-09-30  # procedure step 4 after contrast recovery (contrast 44.2 +/- 2.6 mV, pre-registered rule), apd_state_mapping 83888 --sz-source params --degree 1, new integrator window
        # self.std_n_photons_per_shot = 147.58 #83888, 2026-09-30  # procedure step 5 re-analysis of the step-4 run with t_pi 6.5070e-06 (#83889 joint), apd_mapping_tpi.py 6.507e-6 83888 (apd_state_mapping --sz-source params --degree 1)
        # self.std_n_photons_per_shot = 159.50 #83927, 2026-09-30  # window-mode recal (pre-registered rule, user fallback cycle), apd_state_mapping 83927 --sz-source params --degree 1
        # self.std_n_photons_per_shot = 198.24 #84969, 2026-10-02  # step 4 calibration (feedback procedure 2026-10-02; retry agreeing with 84968), apd_state_mapping 84969 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        self.std_n_photons_per_shot = 143.13 #84975, 2026-10-02  # user-requested retry of the step-4 calibration (feedback procedure 2026-10-02), apd_state_mapping 84975 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5 #83201-83202, 2026-09-27  # linear map (quadratic term not resolved)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83217, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83217
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83227, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83227 --degree 1 (linear fallback, user-approved: curvature resolved, midpoint outside 0.35-0.65)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83237, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83237 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83246, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83246 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83257, 2026-09-27  # overnight auto-recal (user-approved), apd_state_mapping 83257 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83284, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83284 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83294, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83294 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83304, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83304 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83314, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83314 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83324, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83324 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83334, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83334 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83345, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83345 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83350, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83350 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83357, 2026-09-28  # overnight auto-recal (user-approved), apd_state_mapping 83357 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83473, 2026-09-28  # procedure step 4 APD calibration, 7 pts x 5, SLM mask written every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83473, 2026-09-28  # procedure step 4 re-analysis with t_pi 6.1713e-06 (#83474), SLM mask every shot (user-approved), apd_state_mapping 83473 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83520, 2026-09-28  # contrast re-check after the SLM check + joint 83518 (user-approved write-back), retry after 83519 suspicious, apd_state_mapping 83520 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83526, 2026-09-28  # hourly recal (feedback procedure, user-approved), rabi_posterior_cli 83526 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83640, 2026-09-29  # joint recal accepted after the recovery (rise rule 06:4x, user-approved write-backs), rabi_posterior_cli 83640 joint, midpoint pinned 0.5; n_photons rescaled by the contrast, std_n kept
        # self.feedback_measurement_midpoint_fraction = 0.5 #83676, 2026-09-29  # linear map (quadratic term not resolved), apd_state_mapping 83676 --sz-source params --degree 1, new integrator window (gate delay 0.7 / extra 1.0 / settle 4.0 us)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83888, 2026-09-30  # procedure step 4 after contrast recovery (contrast 44.2 +/- 2.6 mV, pre-registered rule), apd_state_mapping 83888 --sz-source params --degree 1, new integrator window
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83888, 2026-09-30  # procedure step 5 re-analysis of the step-4 run with t_pi 6.5070e-06 (#83889 joint), apd_mapping_tpi.py 6.507e-6 83888 (apd_state_mapping --sz-source params --degree 1)
        # self.feedback_measurement_midpoint_fraction = 0.5000 #83927, 2026-09-30  # window-mode recal (pre-registered rule, user fallback cycle), apd_state_mapping 83927 --sz-source params --degree 1
        # self.feedback_measurement_midpoint_fraction = 0.5000 #84969, 2026-10-02  # step 4 calibration (feedback procedure 2026-10-02; retry agreeing with 84968), apd_state_mapping 84969 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)
        self.feedback_measurement_midpoint_fraction = 0.5000 #84975, 2026-10-02  # user-requested retry of the step-4 calibration (feedback procedure 2026-10-02), apd_state_mapping 84975 --sz-source params --degree 1 (Rabi frequency from the joint calibration, linear)

        # run 76228 | multi-parameter grid fit result
        # self.back_action_coherence = 0.7925
        # run 78313 | FeedbackReplayOptimizer, APD-MSE, frequency_lightshift pinned
        # at the 59 kHz above, 2026-09-03. Cuts the grouped APD MSE 0.0377 -> 0.0165.
        # BOUNDED FROM ABOVE ONLY: the loss rises steeply past ~0.7 but is nearly
        # flat below it (0.0165 here vs 0.025 at C = 0.05), so 0.62 is a shallow
        # minimum, conditional on the light-shift pin. Residuals are still 83x the
        # APD error bars, so the model does not yet describe run 78313.
        # self.back_action_coherence = 0.62
        # run 83203 | RabiJointPosterior, nuisances verdict PASS (83195 gave 0.712 +/- 0.018: 2.8 sigma apart)
        # self.back_action_coherence = 0.7746  # +/- 0.0138 #83203, 2026-09-27
        # run 83474 | RabiJointPosterior (f_rabi free), nuisances verdict PASS
        # self.back_action_coherence = 0.7562  # +/- 0.0206 #83474, 2026-09-28
        # run 83889 | RabiJointPosterior (f_rabi free), nuisances verdict PASS, new integrator window
        self.back_action_coherence = 0.7215  # +/- 0.0282 #83889, 2026-09-30

        self.feedback_measurement_midpoint_remap_enabled = True

        # run 66415
        self.feedback_apd_map_enabled = False
        self.feedback_apd_map_a = 0.792175653
        self.feedback_apd_map_b = 0.126581972
        self.feedback_apd_map_verbose = True

        ### timing
        self.t_between_pulses_mu = int64(0)
        self.t_calculation_slack_compensation_mu = int64(0.7 * self.feedback_grid_size * 1.e3) + 15000 if self.feedback_grid_size > 10 else int64(10000)
        # +10 us for the new integrator window (main, 2026-09-29 16:30): the APD sample now lands
        # 5.7 us after the imaging pulse (was 1.0 us), 4.7 us out of the post-sample budget
        # (~47 -> ~42 us vs a ~16 us posterior); +10 us restores it with ~5 us more margin
        # against the rare ~40 us DRTIO stall (83670-83672). User: "increase slack as necessary",
        # 2026-09-29. 29.7 us -> 39.7 us at grid 21.
        self.t_calculation_slack_compensation_mu = self.t_calculation_slack_compensation_mu + int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(800) & ~7 # int64(1260)
        # self.delta_t_mu = int64(2000)

        self.t_ffu_dds_pipeline_latency = int64(79)
        self.t_io_update_pretrigger_mu = int64(32)
        self.t_ffu_pipeline_latency_fudge_mu = int64(0)

        ### randomized raman pulse times
        # Each shot's list of N_pulses raman pulse times (uniform in
        # [min_frac, max_frac] * t_raman_pi_pulse) is a pure function of
        # t_raman_pulse_seed: equal seeds give identical lists, so the seed can
        # be scanned with xvar. t_raman_pulse_seed = 0 --> a fresh seed is drawn
        # for every shot. The seed actually used is saved per shot in
        # data.t_raman_pulse_seed and the drawn times in data.t_raman_pulse
        # (see FeedbackExpt.get_new_t_raman_pulse_list).
        self.t_raman_pulse_random_bool = 1
        self.t_raman_pulse_seed = 532
        self.t_raman_pulse_min_frac_pi = 1/2
        self.t_raman_pulse_max_frac_pi = 1
        # per-shot drawn pulse times; populated in finish_prepare / scan_kernel
        self.t_raman_pulse_list = np.array([self.t_raman_pulse])

        ### other
        self.pulse_list_span_Omega = 0.
        self.pulse_list_seed = 0
        self.phase_offset = 0.0
        # 1: FeedbackExpt rewrites the SLM phase-dot mask every shot (see
        # base_expt_feedback.scan_kernel); 0: only at init_kernel (as before 2026-09-28)
        # self.slm_mask_every_shot = 0
        self.slm_mask_every_shot = 1 # 2026-09-30: default on for every FeedbackExpt (user: all APD experiments write the SLM mask per shot; 83472/83473 contrast 32 -> 14 mV with init-only)
        # 1: every shot starts with APD read (all up) - resonant pi pulse - APD read
        # (all down), stored in data.preshot_apd [up, down] (a per-run contrast), and the
        # feedback model starts all down. FeedbackExpt.finish_prepare derives
        # feedback_initial_sz from it (-1 with the pre-shot, +1 without); runs without
        # the key replay as spin-up (user, 2026-09-28).
        self.preshot_contrast = 0
        self.t_preshot_gap = 10.e-6
        self.feedback_initial_sz = 1.0
        # With the pre-shot: > 0 moves the APD endpoints every shot toward the
        # pre-shot reads, v <- v + gain*(read - v), from the calibration at the start
        # of each run; N_photons_per_shot rescales with the contrast, std_n is kept
        # (Feedback.update_shot_endpoints). 0 = the calibration for every shot.
        # Offline test 2026-09-28 (sim_preshot): 1 (raw per shot) was worse than the
        # calibration, 0.15 better when the readout drifted.
        self.preshot_endpoint_gain = 0.
        # a per-shot range below this x the calibration range is not taken (guard)
        self.preshot_endpoint_min_range_fraction = 0.25

        self.t_tweezer_hold = 30.e-3


