# HF tweezer cold cloud with the painting finish -- the run file of 2026-10-20's REP series, copied into the repo
# unchanged from C:\lab\skynet_log\outputs\2026-10-19_17-20_hf_bec_paint_evap\run_REP_38.py (2026-10-20, at the user's
# request). REP_1..REP_37 = runs 87371-87407 ran this code (REP_38 = 87408 aborted by a person at shot 30).
# Settings (scanning()): the replicated painting finish of PG 87350 + PR 87354 -- evap 1 at 193.0 A, paint -2.92 V,
# exponent 1/3, 1.0 s, tau t/3, end 0.13 V, then a 300 ms paint-up to -4.1 V at held power; evap 2 off (PID2 gives
# no tweezer light, 10-19); f1m1 imaging, 3.5 ms TOF, 50 repeats; upstream = library.
# Result then: N (25 px aperture) ~850-1100 per run, peak OD 0.38-0.49, sigma ~10 um. No condensate established: the
# shape fits' false-positive rate on these data was high (session log 2026-10-19_17-20_1.md, 08:15).
# After a long idle the tweezer light starts low (AO2 thermal, 10-20) and the -4.1 V paint-up can lose every atom
# (87362): use more warm-ups (the REP loop used 20 on its first run after idle) or let the light recover.
# The knob comments below are the run templates' own; their agents/... paths are in that outputs folder.
#
# REP run file (coordinator) -- derived from run_PR_example.py; originally generated from agents/painting/hf_bec_base_paint.py by gen_run.py (scan_PR_replication.txt, 3 warm-ups).
# Agent run template "paint" (painting agent, 2026-10-19 21:xx) = template 5 (agents/creative/hf_bec_base5.py) + two
# painting-LAW knobs for tweezer evap 1. Both default to "off" = template 5's law paint_frac = (v/v_max)**paint_amp_exponent
# (same expression, same branch; checked on the host in prepare(): default law == library law to 1e-12).
#  * p.paint_gamma (default 1. = off): progress warp AT FIXED ENDPOINTS. With q = v/v_max, q_end = v_end/v_max,
#    f_end = q_end**e (e = paint_amp_exponent) and s = ln q / ln q_end (0 at the ramp start, 1 at its end):
#        paint_frac = f_end ** (s ** paint_gamma)
#    gamma = 1 is algebraically the power law (v/v_max)**e; gamma > 1 keeps the painting near full for longer and removes
#    it late (wide/dilute trap while hot, compression at the end); gamma < 1 removes it early (compress first, then
#    evaporate in the narrow trap). Painting at the ramp start (1) and END (f_end) are unchanged -> every arm ends in the
#    SAME trap (same power, same painting voltage), so 3.5 ms TOF numbers compare directly.
#  * p.paint_r (default -1. = off): WAIST-CORRECTED constant-trap-frequency law. The library law assumes the painted width
#    is proportional to the painting amplitude; the x-Basler diag frames (painting agent, runs 87311-87327) show the
#    painted rms width is sigma_y = sqrt(sigma_0^2 + (k (V - V_min))^2) with k (V_max - V_min) = r * sigma_0, r ~ 1.7-2.0 at
#    -2.92 V (camera plane). Holding sigma_y proportional to P**e (the law's own intent) needs
#        paint_frac = sqrt(max(0, (1 + r^2) q**(2e) - 1)) / r      (clipped to [0, 1])
#    which reaches zero painting at q = (1 + r^2)**(-1/(2e)) instead of approaching it asymptotically.
# The two knobs are mutually exclusive (host guard), only for evap 1 on PID1 (refused with do_evap2 = 1), and the law is
# evaluated on the host for every scanned value before the run: paint_frac must be finite and in [0, 1], so the painting
# voltage stays within [V_min = -4.985 V, v_hf_tweezer_paint_amp_max] (the same range template 5 uses).
# Kernel cost: one log + one pow + one exp per ramp step (200 steps over >= 0.5 s: >= 2.5 ms per step).
# End state / error state / hardware: identical to template 5 (only the VALUE written to the painting DAC, Zotino ch 16,
# during evap 1 changes; no new channels, no new timing). tweezer.off() in scan/warm-up kernels; cleanup_scan_kernel ->
# reset_coils; cleanup_abort_kernel on other kernel exceptions.
#
# Agent run template 5 (creative agent, 2026-10-19 20:4x) = template 3 (agents/plan_evap/hf_bec_base3.py) + four knobs.
# EVERY knob defaults to "off", which runs template 3's code path unchanged (same calls, same arguments):
#  * p.i_evap1_field_end (default -1. = off): when >= 0, tweezer evap 1 runs in evap1_with_field_ramp(), a copy of
#    PaintedBeam._ramp_exponential (same coefficients, steps, paint law, tau) that ALSO steps the outer-coil SUPPLY set point
#    linearly in time from p.i_hf_tweezer_evap1_current (step 0) to p.i_evap1_field_end (last step). The coil write
#    (Zotino ch 9, outer_coil_supply_current) is queued with load_dac=False and latched by the tweezer's own LDAC (ch 12/16
#    are on the same Zotino), so field and power move on the same edge. Supply-only control, as in the library evap
#    (no PID); the supply's ~30 ms analog lag applies as it does to every ramp_supply. outer_coil.i_supply is updated,
#    so the following ramp_supply(20 ms -> i_hf_raman) starts from the right current.
#  * p.img_f1m1_hz_per_amp (default 0. = off): imaging detuning = frequency_detuned_hf_f1m1
#    + img_f1m1_hz_per_amp * (i_hf_raman - 182.). For imaging at a field other than 182 A (release at the evap field).
#  * p.v_pd_post_evap (default -1. = off) and p.v_paint_post_evap (default 100. = off), both over p.t_post_evap_ramp:
#    after evap 1, before the field ramp to i_hf_raman, a LINEAR co-ramp of PID1 power (evap-1 end -> v_pd_post_evap)
#    and painting voltage (its value at the evap-1 end -> v_paint_post_evap); a knob that is off holds its value.
#    Both latched on one LDAC edge per step (200 steps). Painting floor: V_TWEEZER_PAINT_MIN -4.985 V = no painting.
# Host guard (prepare): refuses to run if any outer-coil current requested in the tweezer stage (fixed or scanned:
# i_hf_tweezer_load_current, i_hf_tweezer_evap1_current, i_evap1_field_end, i_hf_raman) exceeds 195.25 A, if
# v_pd_post_evap > 10 V, or if v_paint_post_evap is on and outside [-4.985, 6] V.
# End state / error state: as template 3 (tweezer.off() in scan/warm-up kernels; cleanup_scan_kernel -> reset_coils;
# cleanup_abort_kernel on other kernel exceptions). The new loops touch only the outer-coil supply DAC, PID1 DAC and the
# tweezer painting DAC -- channels template 3 already drives. No new hardware.
#
# Agent run template 3 (planner plan_evap, 2026-10-19 18:3x) = template 2 (hf_bec_base2.py) + two run-copy knobs,
# both written so that their DEFAULTS reproduce the last known-good BEC sequence (tools/auto_tof.py, run 86700):
#  * p.do_evap2 (default 1.): tweezer evap 2 on the low-power PID2, cooling.py:139-144 verbatim
#    (exponential_ramp t_hf_tweezer_1064_rampdown2, vpd1_to_vpd2(evap-1 end) -> v_pd_hf_tweezer_1064_rampdown2_end,
#    paint=True, constant-trap-frequency law, low_power=True, tau = default t/3). 0. = template 2 behaviour.
#    Keep v_pd_hf_tweezer_1064_rampdown2_end below tweezer_vpd1_to_vpd2(v_pd_hf_tweezer_1064_rampdown_end), or evap 2 ramps UP.
#  * p.img_f1m1 (default 1.): image on resonance for |1,-1> at i_hf_raman (frequency_detuned_hf_f1m1, as auto_tof.py:53)
#    instead of frequency_detuned_hf_midpoint (48.5 MHz = 8 Gamma away, cross section / 259). 0. = template 2 imaging
#    (use 0. only for in-trap shots, where the resonant OD would be far too high).
# End state / hardware: identical to template 2 plus PID2 enable (ttl) during evap 2, which tweezer.off() clears
# (awg_tweezer.py:132) in scan_kernel and warmup_kernel.
#
# Agent run template 2 (2026-10-19 18:0x), from hf_bec_paint_evap.py (run-1 copy of default_experiments/hf_tweezer_bec.py).
# Adds two run-copy-only knobs, both defaulting to the current library behaviour:
#  * p.paint_amp_exponent (default 0.3333, the hard-coded value in waxx PaintedBeam._paint_amp_v): the tweezer's
#    constant-trap-frequency painting law paint_frac = (P/P_max)**exponent, via a subclass of the kexp tweezer
#    controller swapped in on this run's instance only. The repo is not changed.
#  * p.evap1_tau_frac (default 1/3): tweezer evap-1 exponential ramp tau = t_hf_tweezer_1064_rampdown * frac
#    (exponential_ramp's own default is tau = t/3; negative flips the curvature).
# prep_hf_tweezers_evap1() is cooling.prepare_hf_tweezers(do_tweezer_evap_2=False) line for line, except that tau.

import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras, Adjust
from kexp.control.awg_tweezer import tweezer as kexp_tweezer
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from artiq.language.core import now_mu, at_mu
from waxx.control.artiq.ramp_math import exponential_coeffs
from waxx.control.painted_beam import DAC_PRIMARY

I_TWEEZER_STAGE_MAX = 195.25  # A, outer coil, tweezer stage (coordinator's limit)
V_PAINT_MIN = -4.985          # awg_tweezer.V_TWEEZER_PAINT_MIN
from numpy import log as np_log, exp as np_exp, sqrt as np_sqrt


class tweezer_paint_exp(kexp_tweezer):
    @portable
    def _paint_amp_v(self, v_pd, v_pd_max, v_awg_am_max) -> TFloat:
        p_frac = v_pd / v_pd_max
        if (self.params.paint_gamma == 1.) and (self.params.paint_r < 0.):
            paint_amp_frac = p_frac**self.params.paint_amp_exponent
        else:
            paint_amp_frac = self._paint_frac_ext(p_frac, v_pd_max)
        return (paint_amp_frac - 0.5)*(v_awg_am_max - self.v_paint_min) \
            + (v_awg_am_max + self.v_paint_min)/2

    @portable
    def _paint_frac_ext(self, p_frac, v_pd_max) -> TFloat:
        e = self.params.paint_amp_exponent
        f = 0.
        if self.params.paint_r > 0.:
            # waist-corrected constant-trap-frequency law
            r = self.params.paint_r
            x = (1. + r*r) * p_frac**(2.*e) - 1.
            if x < 0.:
                x = 0.
            f = np_sqrt(x) / r
        else:
            # progress warp at fixed endpoints
            q_end = self.params.v_pd_hf_tweezer_1064_rampdown_end / v_pd_max
            s = np_log(p_frac) / np_log(q_end)
            if s < 0.:
                s = 0.
            if s > 1.:
                s = 1.
            f = np_exp((s**self.params.paint_gamma) * e * np_log(q_end))
        if f > 1.:
            f = 1.
        if f < 0.:
            f = 0.
        return f


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=3)

        self.tweezer.__class__ = tweezer_paint_exp
        self.p.paint_amp_exponent = 0.3333
        self.p.paint_gamma = 1.
        self.p.paint_r = -1.
        self.p.evap1_tau_frac = 1./3.
        self.p.do_evap2 = 1.
        self.p.img_f1m1 = 1.
        self.p.i_evap1_field_end = -1.
        self.p.img_f1m1_hz_per_amp = 0.
        self.p.v_pd_post_evap = -1.
        self.p.v_paint_post_evap = 100.
        self.p.t_post_evap_ramp = 50.e-3

        self.p.t_mot_load = 1.0
        self.p.t_tweezer_hold = 100.e-3
        self.p.t_tof = 3.5e-3

        self.data.apd = self.data.add_data_container(1)

        self.p.N_repeats = 3

        self.scanning()
        self._check_limits()
        self._check_paint_law()
        self.finish_prepare(shuffle=True)

    def _all_values(self, key):
        vals = [np.atleast_1d(np.asarray(getattr(self.p, key), dtype=float))]
        vals += [np.atleast_1d(np.asarray(x.values, dtype=float)) for x in self.scan_xvars if x.key == key]
        return np.concatenate([v.ravel() for v in vals])

    def _check_limits(self):
        for key in ('i_hf_tweezer_load_current', 'i_hf_tweezer_evap1_current', 'i_evap1_field_end', 'i_hf_raman'):
            v = self._all_values(key)
            if np.any(v > I_TWEEZER_STAGE_MAX):
                raise ValueError(f'{key} requests {v.max()} A > {I_TWEEZER_STAGE_MAX} A (tweezer-stage limit)')
        v = self._all_values('v_pd_post_evap')
        if np.any(v > 10.):
            raise ValueError('v_pd_post_evap > 10 V')
        v = self._all_values('v_paint_post_evap')
        v = v[v < 50.]
        if np.any(v < V_PAINT_MIN) or np.any(v > 6.):
            raise ValueError('v_paint_post_evap outside [-4.985, 6] V')

    def _check_paint_law(self):
        # evaluate the evap-1 painting law on the host for every combination of the law-relevant values (fixed or scanned)
        import itertools
        keys = ('paint_gamma', 'paint_r', 'paint_amp_exponent', 'v_pd_hf_tweezer_1064_rampdown_end',
                'v_pd_hf_tweezer_1064_ramp_end', 'v_hf_tweezer_paint_amp_max')
        vals = [np.unique(self._all_values(k)) for k in keys]
        saved = {k: getattr(self.p, k) for k in keys}
        nondefault = False
        try:
            for combo in itertools.product(*vals):
                for k, v in zip(keys, combo):
                    setattr(self.p, k, float(v))
                g, r, e, v_end, v_max, vam = combo
                if (g != 1.) or (r > 0.):
                    nondefault = True
                if (g != 1.) and (r > 0.):
                    raise ValueError('paint_gamma and paint_r are mutually exclusive')
                if not (0.2 <= g <= 5.):
                    raise ValueError(f'paint_gamma {g} outside [0.2, 5]')
                if r > 20.:
                    raise ValueError(f'paint_r {r} > 20')
                if not (0. < v_end < v_max):
                    raise ValueError('need 0 < v_pd_hf_tweezer_1064_rampdown_end < v_pd_hf_tweezer_1064_ramp_end')
                vv = np.geomspace(v_end, v_max, 400)
                pv = np.array([self.tweezer._paint_amp_v(x, v_max, vam) for x in vv])
                lo, hi = min(V_PAINT_MIN, vam), max(V_PAINT_MIN, vam)
                if (not np.all(np.isfinite(pv))) or np.any(pv < lo - 1e-9) or np.any(pv > hi + 1e-9):
                    raise ValueError(f'painting law out of range for {dict(zip(keys, combo))}')
                if (g == 1.) and (r < 0.):
                    lib = ((vv / v_max)**e - 0.5)*(vam - V_PAINT_MIN) + (vam + V_PAINT_MIN)/2
                    if np.max(np.abs(pv - lib)) > 1e-12:
                        raise ValueError('default painting law differs from template 5')
        finally:
            for k, v in saved.items():
                setattr(self.p, k, v)
        if nondefault and np.any(self._all_values('do_evap2') == 1.):
            raise ValueError('paint_gamma / paint_r are for evap 1 only: set do_evap2 = 0')

    def scanning(self):

        # coordinator REP (2026-10-20, user: "just running 3.5ms tof repeats with the current best evap settings, 50 repeats per
        # run, continue til I stop you"). Best evap settings = the replicated painting finish (PG 87350 + PR 87354): evap 1 at
        # 193.0 A, paint -2.92 V, exponent 1/3, 1.0 s, tau t/3, end 0.13 V, then 300 ms paint-up to -4.1 V at held power; evap 2 off;
        # f1m1 imaging, 3.5 ms TOF. Upstream (MOT 1.0 s, 21 A, CMOT, GM, magtrap, sheet) = library. Single-value xvar, 50 repeats.
        self.p.do_evap2 = 0.
        self.p.img_f1m1 = 1.
        self.p.N_repeats = 50
        self.p.v_hf_tweezer_paint_amp_max = -2.92
        self.p.t_hf_tweezer_1064_rampdown = 1.0
        self.p.i_hf_tweezer_evap1_current = 193.0
        self.p.t_post_evap_ramp = 0.3
        self.p.v_pd_hf_tweezer_1064_rampdown_end = 0.13
        self.p.v_paint_post_evap = -4.1
        self.xvar('t_tof',np.array([3.5e-3]))

    @kernel
    def prep_hf_tweezers_evap1(self):
        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)

        self.set_shims(0.,0.,0.)

        # lightsheet evap 1
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_end=self.p.i_hf_tweezer_load_current)

        self.tweezer.on()
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False,
                          tau=-self.p.t_hf_tweezer_1064_ramp/3)
        self.diag.img_tweezer_load_x.trigger()
        self.diag.img_tweezer_pickoff.trigger()

        # lightsheet ramp down (to off)
        self.lightsheet.exponential_ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        if self.p.v_pd_lightsheet_rampdown3_end == 0.:
            self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                             i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1 (painting law set by p.paint_amp_exponent; curvature by p.evap1_tau_frac)
        if self.p.i_evap1_field_end < 0.:
            self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                              v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                              v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                              tau=self.p.t_hf_tweezer_1064_rampdown*self.p.evap1_tau_frac,
                              paint=True,keep_trap_frequency_constant=True)
        else:
            self.evap1_with_field_ramp()

        # tweezer evap 2 (low-power PID2), cooling.py:139-144 verbatim, switched by p.do_evap2
        if self.p.do_evap2 == 1.:
            self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                            v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown_end),
                            v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                            paint=True,keep_trap_frequency_constant=True,low_power=True)

        if (self.p.v_pd_post_evap >= 0.) or (self.p.v_paint_post_evap < 50.):
            self.post_evap_coramp()

        self.diag.img_tweezer_evap_x.trigger()

        self.dac.supply_current_2dmot.set(v=0.)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_end=self.p.i_hf_raman)

        self.outer_coil.start_pid()

        delay(30.e-3)

    @kernel(flags={"fast-math"})
    def evap1_with_field_ramp(self):
        # = tweezer.exponential_ramp(t_hf_tweezer_1064_rampdown, ramp_end -> rampdown_end, tau = t*evap1_tau_frac,
        #   paint=True, keep_trap_frequency_constant=True, PID1) as PaintedBeam._ramp_exponential does it,
        #   plus a linear-in-time outer-coil supply ramp i_hf_tweezer_evap1_current -> i_evap1_field_end on the same LDAC.
        t = self.p.t_hf_tweezer_1064_rampdown
        v_start = self.p.v_pd_hf_tweezer_1064_ramp_end
        v_end = self.p.v_pd_hf_tweezer_1064_rampdown_end
        tau = t*self.p.evap1_tau_frac
        n_steps = self.p.n_tweezer_ramp_steps
        v_pd_max = self.p.v_pd_hf_tweezer_1064_ramp_end
        v_awg_am_max = self.p.v_hf_tweezer_paint_amp_max
        i_start = self.p.i_hf_tweezer_evap1_current
        i_end = self.p.i_evap1_field_end
        di_step = (i_end - i_start)/float(n_steps - 1)

        a, k, e_end = exponential_coeffs(t, v_start, v_end, n_steps, tau)
        e = 1.
        dt_mu = self.core.seconds_to_mu(t / n_steps)

        self.tweezer._ramp_begin(v_start, True, DAC_PRIMARY, dt_mu)

        t_mu = now_mu()
        for i in range(n_steps):
            at_mu(t_mu)
            self.outer_coil.set_supply(i_start + float(i)*di_step, load_dac=False)
            self.tweezer._write_step(v_end + a * (e - e_end), True, v_pd_max,
                                     v_awg_am_max, True, DAC_PRIMARY)
            e *= k
            t_mu += dt_mu
        at_mu(t_mu)
        self.tweezer._ramp_end(v_end, DAC_PRIMARY)
        self.outer_coil.i_supply = i_end

    @kernel(flags={"fast-math"})
    def post_evap_coramp(self):
        # linear co-ramp of PID1 power and painting voltage after evap 1; a knob that is off holds its value
        n_steps = 200
        v0 = self.tweezer.pid1_dac.v
        p0 = self.tweezer.paint_amp_dac.v
        v1 = v0
        p1 = p0
        if self.p.v_pd_post_evap >= 0.:
            v1 = self.p.v_pd_post_evap
        if self.p.v_paint_post_evap < 50.:
            p1 = self.p.v_paint_post_evap
        dv_step = (v1 - v0)/float(n_steps - 1)
        dp_step = (p1 - p0)/float(n_steps - 1)
        dt_mu = self.core.seconds_to_mu(self.p.t_post_evap_ramp / n_steps)
        t_mu = now_mu()
        for i in range(n_steps):
            at_mu(t_mu)
            self.tweezer._set_pd(v0 + float(i)*dv_step, DAC_PRIMARY)
            self.tweezer.paint_amp_dac.set(p0 + float(i)*dp_step, load_dac=False)
            self.tweezer._load_pd(DAC_PRIMARY)
            t_mu += dt_mu
        at_mu(t_mu)
        self.tweezer._ramp_end(v1, DAC_PRIMARY)

    @kernel
    def warmup_kernel(self):
        # same preparation as scan_kernel, no imaging
        self.prep_hf_tweezers_evap1()
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        self.lightsheet.off()
        delay(self.p.t_tof)

    @kernel
    def scan_kernel(self):
        if self.p.img_f1m1 == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1
                                      + self.p.img_f1m1_hz_per_amp*(self.p.i_hf_raman - 182.))
        else:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)

        self.prep_hf_tweezers_evap1()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, restart_monitor=False)
