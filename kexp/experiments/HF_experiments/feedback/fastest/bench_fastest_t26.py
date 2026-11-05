# bench_cg12_t26, make_cg12.py. No atoms, shutter closed.
# bench_cg7, make_cg7.py. No atoms, shutter closed.
# H0 bench, no atoms, make_s2f_bench.py, from f_cf_s11g5.py. Rule, fpab H0, fixed before the data, scripts/bench_table.py: no underflow, no core log line, >= 10,000 steps, min margin >= 5 us, by step type: pre-issued, not, mode 1-3, reinit, excluding i = 0. bench_margin before the frequency write, bench_margin2 before the pulse. No-atom reads flatten the posterior, so the certainty trigger is forced at K: that path is what is tested, not early firing.
from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, TFloat
import numpy as np
from numpy import int64
from artiq.coredevice.rtio import rtio_output

# module import, not the class: artiq_run refuses a file with two public experiment classes
import kexp.experiments.HF_experiments.feedback.feedback_reinit as fr
from kexp.base.feedback import feedback_grid_derived
from artiq.coredevice.sampler import adc_mu_to_volt, SPI_CONFIG, SPI_CS_ADC
from artiq.coredevice import spi2 as spi
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

# Fastest feedback kernel, make_cf.py: 20 kHz, m 21, slack 11104 ns, i = 0 gap + 5 us. NOT for atoms until the rules of PLAN.md.


from waxx.config.data_vault import DataContainer as _DC

_TRACE = {"t": 0., "key": "start", "n": 0, "total": 0}
_ORIG_UPDATE, _ORIG_PUT = _DC.update_from_kernel, _DC._put_shot_data_to_run_data
_DC._b0, _DC._b1 = 0, 0 # every container the kernel can reach has them, a sub-scan vault's too


def _trace_mark(key):
    import time
    _TRACE["t"], _TRACE["key"] = time.time(), key
    _TRACE["n"] += 1
    _TRACE["total"] += 1


def _traced_update(self, data):
    _trace_mark("update " + self.key)
    return _ORIG_UPDATE(self, data)


def _traced_put(self):
    _trace_mark("store " + self.key)
    return _ORIG_PUT(self)


def _start_trace(name):
    # a stall = no step of the push for 8 s after one has started: one line with the last step, one when it ends
    import threading, time
    _DC.update_from_kernel, _DC._put_shot_data_to_run_data = _traced_update, _traced_put
    path = rf"C:\lab\skynet_log\outputs\2026-10-30_17-54_night_summary\stall_dumps\trace_{name}.log"

    def watch():
        last, inside = 0., False
        with open(path, "a", buffering=1) as f:
            f.write(f"{time.strftime('%H:%M:%S')} trace on {name}\n")
            while True:
                time.sleep(.5)
                now, t, key = time.time(), _TRACE["t"], _TRACE["key"]
                if t and not inside and now - t > 8.:
                    inside, last = True, t
                    f.write(f"{time.strftime('%H:%M:%S')} no step for 8 s, last {key}, step {_TRACE['n']} of this push, {_TRACE['total']} total\n")
                elif inside and t != last:
                    f.write(f"{time.strftime('%H:%M:%S')} moved after {t - last:.1f} s, now {_TRACE['key']}\n")
                    inside = False

    threading.Thread(target=watch, daemon=True).start()


from kexp.experiments.HF_experiments.feedback.data_vault_feedback import DataVault as _DataVaultBase


class BatchVault(_DataVaultBase):
    """End-of-shot push of every float64 container through one flat array. Test code, make_batch_test.py. The order of a list is the order of its containers; offsets are fixed at init. Host side does what update_from_kernel and _put_shot_data_to_run_data do, per container."""
    _batch_chunked = 0
    _batch_size = 128

    def init(self):
        _DataVaultBase.init(self)
        self._batch = []
        o = 0
        for dc in self._list_1d_f64:
            dc._b0, dc._b1 = int(dc.shot_data.shape[0]), 1
            if not dc._is_sentinel:
                self._batch.append((dc, o, dc._b0))
                o += dc._b0
        for dc in self._list_2d_f64:
            dc._b0, dc._b1 = int(dc.shot_data.shape[0]), int(dc.shot_data.shape[1])
            if not dc._is_sentinel:
                self._batch.append((dc, o, dc._b0 * dc._b1))
                o += dc._b0 * dc._b1
        self._flat = np.zeros(o, dtype=np.float64)
        self._flat_n = o
        self._flat_host = np.zeros(o, dtype=np.float64)
        self._chunk = np.zeros(self._batch_size, dtype=np.float64)
        print(f"[batch] {len(self._batch)} float64 containers, {o} doubles, {8 * o} B per shot, chunked {self._batch_chunked}")

    def _batch_fail(self, n):
        # reviewer: a container the host did not size would pack nothing, silently
        raise ValueError(f"BatchVault: packed {n} doubles, expected {self._flat_n}")

    def _batch_split(self, flat):
        for dc, o, n in self._batch:
            dc.update_from_kernel(np.array(flat[o:o + n]).reshape(dc.shot_data.shape))
            dc._put_shot_data_to_run_data()

    def _take_flat(self, flat):
        _trace_mark("flat")
        _TRACE["n"] = 0
        self._batch_split(flat)

    def _take_chunk(self, k, chunk, last):
        _trace_mark(f"chunk at {k}")
        n = min(len(chunk), self._flat_n - k)
        self._flat_host[k:k + n] = chunk[:n]
        if last:
            self._batch_split(self._flat_host)

    @kernel
    def put_shot_data(self):
        self._expt.core.wait_until_mu(now_mu())
        n = 0
        for dc_1d_f64 in self._list_1d_f64:
            if not dc_1d_f64._is_sentinel:
                for j in range(dc_1d_f64._b0):
                    self._flat[n] = dc_1d_f64.shot_data[j]
                    n += 1
        for dc_2d_f64 in self._list_2d_f64:
            if not dc_2d_f64._is_sentinel:
                for i in range(dc_2d_f64._b0):
                    for j in range(dc_2d_f64._b1):
                        self._flat[n] = dc_2d_f64.shot_data[i, j]
                        n += 1
        if n != self._flat_n:
            self._batch_fail(n)
        if self._batch_chunked:
            k = 0
            while k < self._flat_n:
                for j in range(self._batch_size):
                    if k + j < self._flat_n:
                        self._chunk[j] = self._flat[k + j]
                self._take_chunk(k, self._chunk, k + self._batch_size >= self._flat_n)
                k += self._batch_size
        else:
            self._take_flat(self._flat)
        for dc_1d_i32 in self._list_1d_i32:
            dc_1d_i32._put_shot_data()
        for dc_2d_i32 in self._list_2d_i32:
            dc_2d_i32._put_shot_data()
        for dc_1d_i64 in self._list_1d_i64:
            dc_1d_i64._put_shot_data()
        for dc_2d_i64 in self._list_2d_i64:
            dc_2d_i64._put_shot_data()
        self._expt.core.break_realtime()


class bench_cg12_t26(fr.feedback_reinit):
    """Stage-2 feedback (organizer, night 2026-10-30, generated by make_s2f.py). Fast path by default; a row with fast 0 runs the standard path. Arms interleave shot by shot through one
    shuffled xvar, s2_idx, an index into the arm table; each row = arm + initial offset.

    arm 0 production: N1 pulses + reads, no reinit.
    arm 1 stage 2: pulses + reads until the trigger (n >= K_min and (posterior std < thr or n >= K_force)), then
        pole pulse + read (feedback_reinit method 1; pole_read 0: no read);
        reinit (user 2026-10-30): remesh around the MAP with the posterior interpolated; every hypothesis restarts at (0, 0, s), s = the most
        likely point's S_z, reduced by the modelled decoherence. x, y of that point are recorded, not kept: offline no different (s4b_assess);
        then cycles j: equator pulse (length from the posterior-mean a, b: mean S_z -> 0, no read), wait, analysis pulse pi/2, read.
        The equator pulse and the wait run at MAP + steer / (4 T_j), steer = +-1 by row, the side of the fringe: the FTW of the equator pulse is
        the FTW of the wait, so nothing is written mid gap and set(relative_phase) is not used.
    arm 2 tomography: as arm 1 up to the reinit, then one analysis pulse of angle theta (0 = no pulse) after a fixed gap, and a read.
        Rows with dfreq != 0 run the POLE pulse (and so the gap) at MAP + dfreq, which turns the analysis axis by 2 pi dfreq T_gap.
    arm 3 open-loop tomography: fixed drive (update 0), K pulses + reads, no pole, no reinit, then as arm 2: the state is deterministic, so its first
        moments give its length. dfreq goes on pulse K, whose FTW is the FTW of the gap.
    arm 4 Ramsey contrast: no stage 1: equator pulse from the initial state, wait T (ladder of the row), analysis pi/2, read; steer = 0, 1, 2, 3 is the
        analysis phase in units of pi/2.

    Per pulse: data.s2_kind (0 stage 1, 1 pole, 2 equator, 3 analysis, 5 tomography, -1 not played), data.dT_mu (gap after this pulse, ns),
    data.t_raman_pulse (played), data.omega_raman, data.apd (reads only), probabilities + mesh rows. Per shot: reinit_*, s2_smap_x/y/z.
    """

    def prepare(self):

        fr.FeedbackExpt.__init__(self,
                                 save_data=True,
                                 save_on_underflow=True)
        _start_trace("s2f")
        self.data.__class__ = BatchVault

        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1
        self.p.feedback_fractional_initial_offset = 0.
        # added gaps, ns: before the pole, after the pole, after each analysis read (library reinit ran 30 + 30; reviewer 2026-10-30)
        self.p.s2_extra_pre_mu = int64(30000)
        self.p.s2_extra_post_mu = int64(45000)
        self.p.s2_extra_an_mu = int64(20000)
        self.p.feedback_reinit_method = 1
        self.p.feedback_reinit_center_mode = 0
        self.p.feedback_reinit_temper_beta = 1.0

        self.p.t_s2_settle = 405.e-3

        import faulthandler
        faulthandler.dump_traceback_later(60, repeat=True, file=open(r"C:\lab\skynet_log\outputs\2026-10-30_17-54_night_summary\stall_dumps\cf_s11g5.log", "a"))
        self.p.t_raman_pi_pulse = 3.8016e-06
        self.p.t_raman_pulse = 1.9008e-06
        self.p.t_raman_pulse_ideal = 1.7738e-06
        self.p.phase_slm_mask = 1.5707963267948966
        self.p.frequency_detuned_hf_midpoint = -519500000.0
        self.p.frequency_raman_transition = 119463700.0
        self.p.v_apd_all_up = -0.13594
        self.p.v_apd_all_down = -0.1751
        self.p.feedback_measurement_midpoint_fraction = 0.45497
        self.p.std_n_photons_per_shot = 120.78
        self.p.frequency_lightshift = 28100.0
        self.p.read_alpha_lightshift = 0.9613
        self.p.read_twist_per_sz = 0.8913
        s2_pins = {'t_raman_pi_pulse': 3.8016e-06, 't_raman_pulse': 1.9008e-06, 't_raman_pulse_ideal': 1.7738e-06, 'phase_slm_mask': 1.5707963267948966, 'frequency_detuned_hf_midpoint': -519500000.0, 'frequency_raman_transition': 119463700.0, 'v_apd_all_up': -0.13594, 'v_apd_all_down': -0.1751, 'feedback_measurement_midpoint_fraction': 0.45497, 'std_n_photons_per_shot': 120.78, 'frequency_lightshift': 28100.0, 'read_alpha_lightshift': 0.9613, 'read_twist_per_sz': 0.8913}
        self.p.N_warmup_shots = 0
        self.p.t_integrator_settle = 2e-06
        self.p.N_repeats = 45
        self.p.t_raman_pulse_seed = 0
        self.p.t_calculation_slack_compensation_mu = int64(-896)
        self.p.feedback_grid_size = 21
        self.p.frequency_feedback_grid_full_span = 20000.0
        self.p.s2_N1 = 11
        self.p.s2_K_min = 2
        self.p.s2_thr_hz = 0.0
        self.p.s2_span_hz = 6000.0
        self.p.s2_ladders = [[0.0001, 0.00017, 0.00029, 0.0005]]
        self.p.s2_tomo_gap = 0.00012
        self.p.s2_sched_us = [[5.0]]
        self.p.s2_rows = [(0, -0.9473684210526315, 1, 0.0, 0.0, 0.0, 0, -0.4285714285714286, 4, 0, 1, 1), (0, -0.631578947368421, 1, 0.0, 0.0, 0.0, 0, -0.2857142857142857, 4, 0, 1, 1), (0, -0.3157894736842105, 1, 0.0, 0.0, 0.0, 0, -0.14285714285714285, 4, 0, 1, 1), (0, 0.0, 1, 0.0, 0.0, 0.0, 0, 0.0, 4, 0, 1, 1), (0, 0.3157894736842105, 1, 0.0, 0.0, 0.0, 0, 0.1428571428571429, 4, 0, 1, 1), (0, 0.631578947368421, 1, 0.0, 0.0, 0.0, 0, 0.2857142857142857, 4, 0, 1, 1), (0, 0.9473684210526315, 1, 0.0, 0.0, 0.0, 0, 0.4285714285714286, 4, 0, 1, 1), (1, -0.9473684210526315, 1, 0.0, 0.0, 1.0, 0, -0.2857142857142857, 4, 0, 1, 1), (1, -0.631578947368421, 1, 0.0, 0.0, 1.0, 0, -0.14285714285714285, 4, 0, 1, 1), (1, -0.3157894736842105, 1, 0.0, 0.0, 1.0, 0, 0.0, 4, 0, 1, 1), (1, 0.0, 1, 0.0, 0.0, 1.0, 0, 0.1428571428571429, 4, 0, 1, 1), (1, 0.3157894736842105, 1, 0.0, 0.0, 1.0, 0, 0.2857142857142857, 4, 0, 1, 1), (1, 0.631578947368421, 1, 0.0, 0.0, 1.0, 0, 0.4285714285714286, 4, 0, 1, 1), (1, 0.9473684210526315, 1, 0.0, 0.0, 1.0, 0, -0.4285714285714286, 4, 0, 1, 1), (1, -0.9473684210526315, 1, 0.0, 0.0, -1.0, 0, -0.14285714285714285, 4, 0, 1, 1), (1, -0.631578947368421, 1, 0.0, 0.0, -1.0, 0, 0.0, 4, 0, 1, 1), (1, -0.3157894736842105, 1, 0.0, 0.0, -1.0, 0, 0.1428571428571429, 4, 0, 1, 1), (1, 0.0, 1, 0.0, 0.0, -1.0, 0, 0.2857142857142857, 4, 0, 1, 1), (1, 0.3157894736842105, 1, 0.0, 0.0, -1.0, 0, 0.4285714285714286, 4, 0, 1, 1), (1, 0.631578947368421, 1, 0.0, 0.0, -1.0, 0, -0.4285714285714286, 4, 0, 1, 1), (1, 0.9473684210526315, 1, 0.0, 0.0, -1.0, 0, -0.2857142857142857, 4, 0, 1, 1)]

        p = self.p
        t_pi = float(p.t_raman_pi_pulse)
        Omega_hz = 1. / (2. * t_pi)
        ladders = p.s2_ladders
        Lmax = max(len(x) for x in ladders)
        self.p.s2_Lmax = Lmax
        self.p.s2_lad_len = np.array([float(len(x)) for x in ladders])
        flat = np.zeros(len(ladders) * Lmax)
        for q, x in enumerate(ladders):
            flat[q * Lmax:q * Lmax + len(x)] = np.asarray(x, dtype=float)
        self.p.s2_lad_flat = flat
        self.p.feedback_reinit_span_Omega = .5 * p.s2_span_hz / Omega_hz
        self.p.s2_thr_Omega = p.s2_thr_hz / Omega_hz
        self.p.s2_t_pi2 = .5 * t_pi + float(p.t_raman_pulse_offset)
        self.p.s2_tomo_gap_mu = int64(p.s2_tomo_gap * 1.e9) & ~int64(7)
        rows = p.s2_rows                   # (arm, frac offset, pole_read, theta, dfreq Hz, steer, gap schedule, grid shift, K, ladder, update)
        for r in rows:
            assert abs(r[1]) < 1. and r[0] in (0, 1, 2, 3, 4) and abs(r[7]) <= .5 and r[8] >= 1
        self.p.s2_tbl_arm = np.array([float(r[0]) for r in rows] + [-1.])
        self.p.s2_tbl_offset = np.array([feedback_grid_derived(p.frequency_feedback_grid_full_span, p.feedback_grid_size, t_pi, r[1])[1]
                                         for r in rows] + [0.])
        self.p.s2_tbl_pole_read = np.array([float(r[2]) for r in rows] + [-1.])
        self.p.s2_tbl_theta = np.array([float(r[3]) for r in rows] + [-1.])
        self.p.s2_tbl_dfreq = np.array([float(r[4]) for r in rows] + [-1.])
        self.p.s2_tbl_steer = np.array([float(r[5]) for r in rows] + [-1.])
        self.p.s2_tbl_sched = np.array([float(r[6]) for r in rows] + [-1.])
        self.p.s2_tbl_shift = np.array([float(r[7]) for r in rows] + [-1.])
        self.p.s2_tbl_K = np.array([float(r[8]) for r in rows] + [-1.])
        self.p.s2_tbl_lad = np.array([float(r[9]) for r in rows] + [-1.])
        self.p.s2_tbl_update = np.array([float(r[10]) for r in rows] + [-1.])
        self.p.s2_tbl_fast = np.array([float(r[11]) if len(r) > 11 else 1. for r in rows] + [-1.])
        self.p.fast_path = 1 if all((len(r) <= 11 or r[11] == 1) for r in rows) else 0

        def pulses(r):
            n = len(ladders[r[9]])
            return {0: p.s2_N1, 1: r[8] + 1 + 2 * n, 2: r[8] + 2, 3: r[8] + 1, 4: 2 * n}[r[0]]

        n_pulses = int(max(pulses(r) for r in rows))
        del self.p.s2_rows, self.p.s2_ladders
        self.p.N_pulses = n_pulses
        # bounds (reviewer K1): a NaN from the fast-math angle code must not reach delay() or int64()
        self.p.s2_t_pulse_max = 2. * t_pi + float(p.t_raman_pulse_offset)
        self.p.s2_dT_max_mu = (int64(float(np.max(flat)) * 1.e9) + int64(100000)) & ~int64(7)
        self.p.s2_omega_guard = 2. * np.pi * 300.e3
        # extra delay after pulse i of stage 1, schedule q: entry q * n_pulses + i, ns on the 8 ns grid
        sched = np.asarray(p.s2_sched_us, dtype=float)
        n_sched = sched.shape[0]
        flat = np.zeros(n_sched * n_pulses)
        for q in range(n_sched):
            flat[q * n_pulses:q * n_pulses + sched.shape[1]] = (np.rint(sched[q] * 1.e3).astype(np.int64) & ~np.int64(7)).astype(float)
        self.p.s2_sched_flat = flat
        del self.p.s2_sched_us
        self.p.s2_idx = 0.
        self.xvar('s2_idx', np.arange(len(rows), dtype=float))

        self.data.reinit_pulse = self.data.add_data_container(1)
        self.data.reinit_trigger_std = self.data.add_data_container(1)
        self.data.reinit_theta = self.data.add_data_container(1)
        self.data.reinit_sz_pred = self.data.add_data_container(1)
        self.data.reinit_sz_meas = self.data.add_data_container(1)
        self.data.reinit_center = self.data.add_data_container(1)
        self.data.s2_smap_x = self.data.add_data_container(1)
        self.data.s2_smap_y = self.data.add_data_container(1)
        self.data.s2_smap_z = self.data.add_data_container(1)
        # per-shot record of the row and the fields that define it: the saved tables are padded, but these need no table at all
        self.data.s2_row = self.data.add_data_container(1)
        self.data.s2_fast = self.data.add_data_container(1)
        self.data.s2_arm = self.data.add_data_container(1)
        self.data.s2_K = self.data.add_data_container(1)
        self.data.s2_lad = self.data.add_data_container(1)
        self.data.s2_steer = self.data.add_data_container(1)
        self.data.s2_theta = self.data.add_data_container(1)
        self.data.s2_dfreq = self.data.add_data_container(1)
        self.data.s2_pole_read = self.data.add_data_container(1)
        self.data.s2_sched = self.data.add_data_container(1)
        self.data.s2_shift = self.data.add_data_container(1)
        self.data.s2_degenerate = self.data.add_data_container(1)
        self.data.s2_clamped = self.data.add_data_container(1)
        self.data.s2_final_map = self.data.add_data_container(1)
        self.data.s2_final_std = self.data.add_data_container(1)
        self.data.s2_n_played = self.data.add_data_container(1)
        self.data.s2_kind = self.data.add_data_container(n_pulses)
        self.data.dT_mu = self.data.add_data_container(n_pulses)
        self.data.bench_margin = self.data.add_data_container(n_pulses)
        self.data.bench_margin2 = self.data.add_data_container(n_pulses)
        self.data.push_pad = self.data.add_data_container(175)

        self.s2_sx = 0.
        self.s2_sy = 0.
        self.s2_sz = 0.
        # refuse a table the save step would permute, before a run id is used
        axes = (len(rows), len(rows) * int(self.p.N_repeats))
        for name in dir(self.p):
            if name.startswith("s2_"):
                val = getattr(self.p, name)
                if isinstance(val, np.ndarray) and val.ndim > 0 and int(val.shape[0]) in axes:
                    raise RuntimeError(f"{name} has the length of a shuffled axis: its saved copy would be permuted")
        self.raman.set_ao_mode(1, float(np.ravel(self.p.frequency_raman_transition)[0]))
        self.raman.prepare_direct_fast_path()
        self.kernel_invariants = set(getattr(type(self), "kernel_invariants", set())) | {"p", "raman", "integrator", "core", "core_dma", "data", "imaging", "hc_t_raman_set_pretrigger_mu", "hc_t_calculation_slack_compensation_mu", "hc_t_img_pulse", "hc_t_fifo_mu", "hc_N_pulses", "hc_s2_N1", "hc_s2_K_min", "hc_s2_sched_flat", "hc_s2_dT_max_mu", "hc_s2_thr_Omega", "hc_s2_omega_guard", "hc_t_io_update_pretrigger_mu", "hc_t_ffu_dds_pipeline_latency", "hc_t_ffu_pipeline_latency_fudge_mu"}
        type(self.raman).kernel_invariants = set(type(self.raman).kernel_invariants) | {"dds0", "dds1", "dds_sw"}
        self.s2_live = 0
        self.finish_prepare()
        for k, v in s2_pins.items():
            assert float(np.ravel(getattr(self.p, k))[0]) == v, k
        self.s2_live = 1
        self.hc_t_raman_set_pretrigger_mu = self.p.t_raman_set_pretrigger_mu
        self.hc_t_calculation_slack_compensation_mu = self.p.t_calculation_slack_compensation_mu
        self.hc_t_img_pulse = self.p.t_img_pulse
        self.hc_t_fifo_mu = self.p.t_fifo_mu
        self.hc_N_pulses = self.p.N_pulses
        self.hc_s2_N1 = self.p.s2_N1
        self.hc_s2_K_min = self.p.s2_K_min
        self.hc_s2_sched_flat = self.p.s2_sched_flat
        self.hc_s2_dT_max_mu = self.p.s2_dT_max_mu
        self.hc_s2_thr_Omega = self.p.s2_thr_Omega
        self.hc_s2_omega_guard = self.p.s2_omega_guard
        self.hc_t_io_update_pretrigger_mu = self.p.t_io_update_pretrigger_mu
        self.hc_t_ffu_dds_pipeline_latency = self.p.t_ffu_dds_pipeline_latency
        self.hc_t_ffu_pipeline_latency_fudge_mu = self.p.t_ffu_pipeline_latency_fudge_mu
        assert int(self.p.include_photon_noise) == 1
        assert int(self.integrator.sampler_ch.ch) == 7
        assert not [x.key for x in self.scan_xvars if x.key in ('t_img_pulse', 't_integrator_gate_delay', 't_integrator_gate_extra', 't_integrator_settle')]
        self.p1_scratch = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.t_sample_mu = int64(0)
        self.t_sample_next_mu = int64(0)
        self.cf_off = int64(0)
        self.hot_gap_mu = int64(self.p.t_calculation_slack_compensation_mu) + int64(self.p.t_raman_set_pretrigger_mu) + int64(float(self.p.t_img_pulse) * 1.e9) + int64(self.p.t_fifo_mu)
        assert int(self.hot_gap_mu) % 8 == 0 and int(self.hot_gap_mu) > 0
        self.hot_gain = 0
        self.hot_dt0 = int64(0)
        self.hot_dt1 = int64(0)

    @portable(flags={"fast-math"})
    def reset_initial_omega_from_params(self):
        # the offset comes from the arm table, so arms and offsets shuffle as one xvar. s2_live 0: on the host inside finish_prepare, s2_idx is still the scan array
        if self.s2_live == 1:
            self.p.feedback_initial_offset_Omega = self.p.s2_tbl_offset[int(self.p.s2_idx)]
            self.p.feedback_grid_shift = self.p.s2_tbl_shift[int(self.p.s2_idx)]
        self.omega_raman = (
            2.0 * np.pi * self.p.frequency_raman_transition
            + self.Omega * self.p.feedback_initial_offset_Omega
        )
        return self.omega_raman

    @portable(flags={"fast-math"})
    def rotate_only(self, t, phase_raman_pulse_start):
        """Rotation part of feedback_reinit.propagate_hypotheses for a pulse with NO read: no read light shift, no twist, no coherence loss."""
        omega_guess_list = self.omega_guess_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        m = self.m
        omega_raman = self.omega_raman
        Omega = self.Omega
        Omega_sq = Omega * Omega
        dt_eff = self.t_raman_pulse_current
        dt_ideal = self.t_raman_pulse_ideal_current
        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0
        omega0 = omega_guess_list[0]
        phi = phase_raman_pulse_start - omega0*t
        delta_omega0 = omega0 - omega_raman
        (sin_wt, cos_wt) = self.sincos_lut_interp(phi)
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(-domega * t)
        alpha_z = dt_eff * delta_omega0
        (sin_z, cos_z) = self.sincos_lut_interp(alpha_z)
        alpha_z_step = dt_eff * domega
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(alpha_z_step)
        j = 0
        while j < m:
            omega = omega_guess_list[j]
            delta_omega = omega_raman - omega
            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H
                (sin_H, cos_H) = self.sincos_lut_interp(-dt_ideal * norm_H)
            else:
                Omega_over_H = 0.0
                u_z = 0.0
                sin_H = 0.0
                cos_H = 1.0
            sx = state_x[j]
            sy = state_y[j]
            sz = state_z[j]
            u_x = Omega_over_H * cos_wt
            u_y = Omega_over_H * sin_wt
            one_minus_cos = 1.0 - cos_H
            uxux = u_x * u_x
            uyuy = u_y * u_y
            uzuz = u_z * u_z
            uxuy = u_x * u_y
            uxuz = u_x * u_z
            uyuz = u_y * u_z
            hx = (cos_H + one_minus_cos * uxux) * sx
            hx += (one_minus_cos * uxuy - sin_H * u_z) * sy
            hx += (one_minus_cos * uxuz + sin_H * u_y) * sz
            hy = (one_minus_cos * uxuy + sin_H * u_z) * sx
            hy += (cos_H + one_minus_cos * uyuy) * sy
            hy += (one_minus_cos * uyuz - sin_H * u_x) * sz
            hz = (one_minus_cos * uxuz - sin_H * u_y) * sx
            hz += (one_minus_cos * uyuz + sin_H * u_x) * sy
            hz += (cos_H + one_minus_cos * uzuz) * sz
            state_x[j] = cos_z * hx + sin_z * hy
            state_y[j] = -sin_z * hx + cos_z * hy
            state_z[j] = hz
            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            next_cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            cos_wt = next_cos_wt
            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            next_cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            cos_z = next_cos_z
            j += 1

    @portable(flags={"fast-math"})
    def equator_angle(self, phase_start, t):
        """theta in [0, pi) taking the posterior-mean S_z to 0: S_z' = b cos(theta) - a sin(theta), notation of pole_ab."""
        am = 0.0
        bm = 0.0
        j = 0
        while j < self.m:
            (a, b) = self.pole_ab(j, phase_start, t)
            am += self.P0[j] * a
            bm += self.P0[j] * b
            j += 1
        theta = np.arctan2(bm, am)
        if theta < 0.0:
            theta += np.pi
        if theta >= np.pi:
            theta -= np.pi
        return theta

    @portable(flags={"fast-math"})
    def reinit_to_map(self):
        """Remesh with the posterior interpolated; every hypothesis restarts at (0, 0, s), s = the most likely point's S_z."""
        best = 0
        pbest = self.P0[0]
        j = 1
        while j < self.m:
            if self.P0[j] > pbest:
                pbest = self.P0[j]
                best = j
            j += 1
        self.s2_sx = self.state_x[best]
        self.s2_sy = self.state_y[best]
        self.s2_sz = self.state_z[best]
        self.max_idx = best
        center = self.reinit_center()
        self.remesh_to_centered(center, self.p.feedback_reinit_span_Omega, 1, 0, 1)
        best = 0
        pbest = self.P0[0]
        j = 0
        while j < self.m:
            self.state_x[j] = 0.0
            self.state_y[j] = 0.0
            self.state_z[j] = self.s2_sz
            if self.P0[j] > pbest:
                pbest = self.P0[j]
                best = j
            j += 1
        self.max_idx = best
        return self.omega_guess_list[best]

    @kernel
    def prepare_hf_tweezers(self,
                            do_tweezer_evap_2=True,
                            ramp_down_painting = False,
                            squeeze=False,
                            cubic_ramp_squeeze=True,
                            ):
        """prepares hf evap tweezers at i_outer = ExptParams.i_non_inter with
        PID enabled.
        """
        if squeeze:
            ramp_down_painting = True


        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # delay(200.e-3)

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
                            #  i_start=self.p.i_hf_lightsheet_evap1_current,
                             i_end=self.p.i_hf_tweezer_load_current)
        
        self.tweezer.on()
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False,
                          tau=-self.p.t_hf_tweezer_1064_ramp/3)
        self.diag.img_tweezer_load_x.trigger()      # diagnostic frames (no-op when off)
        self.diag.img_tweezer_pickoff.trigger()
                          
        # lightsheet ramp down (to off)
        self.lightsheet.exponential_ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        if self.p.v_pd_lightsheet_rampdown3_end == 0.:
            self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                             i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1; painting law (P/P_max)**paint_amp_exponent_hf_tweezer
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True,
                          paint_exponent=self.p.paint_amp_exponent_hf_tweezer)

        if do_tweezer_evap_2:
            # PID2 start biased low: integral2 is preloaded to 4 V (AO2's efficiency peak) at enable
            v_start2 = tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown_end) \
                * self.p.fraction_hf_tweezer_evap2_start
            if self.p.do_hold_painting_hf_tweezer_evap2 == 1.:
                # painting held at its evap-1 end value (keep_trap_frequency_constant=False
                # writes v_awg_am_max every step)
                self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                                v_start=v_start2,
                                v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                                paint=True,keep_trap_frequency_constant=False,
                                v_awg_am_max=self.tweezer.paint_amp_dac.v,
                                low_power=True)
            else:
                self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                                v_start=v_start2,
                                v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                                paint=True,keep_trap_frequency_constant=True,low_power=True,
                                paint_exponent=self.p.paint_amp_exponent_hf_tweezer)

        self.diag.img_tweezer_evap_x.trigger()      # diagnostic frame after the last evap ramp

        self.dac.supply_current_2dmot.set(v=0.)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_end=self.p.i_hf_raman)
        # delay(100.e-3)
        # self.outer_coil.ttl_blanking.off()
        # delay(100.e-3)
        
        self.outer_coil.start_pid()
        
        delay(30.e-3)
        
        
        if squeeze or ramp_down_painting:
            self.ramp_down_painting()

        if squeeze and ramp_down_painting and do_tweezer_evap_2:
            # UNTESTED since 2026-10-21: the squeeze now starts from the new evap-2 end (PID2 0.20 V, was 4.0 V)
            # and hands back to PID1 through the old _squeezer calibration (tweezer.py, "needs recalibration").
            # Validate with a no-atom PD run (like pid2_handoff.py) before trusting squeeze data.
            self.ttl.pd_scope_trig.pulse(1.e-6)
            self.tweezer_squeeze(cubic_ramp_squeeze)

        delay(2.e-3) # slack, as kt_hold2b
        self.ramp_down_painting()
        delay(self.p.t_s2_settle) # 450 ms from evaporation, the 45 ms ramp inside

    @portable(flags={"fast-math"})
    def propagate_hypotheses(self, t, phase_raman_pulse_start=0.):
        omega_guess_list = self.omega_guess_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        p1s = self.p1_scratch
        m = self.m
        omega_raman = self.omega_raman
        Omega = self.Omega
        Omega_sq = Omega * Omega
        dt_eff = self.t_raman_pulse_current
        dt_ideal = self.t_raman_pulse_ideal_current
        dt_z = self.p.t_img_pulse
        twist_on = self.read_twist_on
        twist = self.read_twist
        coherence0 = self.back_action_coherence
        slope_on = self.read_coherence_slope_on
        slope = self.read_coherence_slope
        remap = self.feedback_measurement_midpoint_remap_enabled
        two_pi = self.two_pi
        inv_two_pi = self.inv_two_pi
        lut_scale = self.lut_scale
        lut_mask = self.lut_mask
        lut_quarter = self.lut_quarter
        sin_lut = self.sin_lut
        mid = self.feedback_measurement_midpoint_fraction - 0.5
        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0
        omega0 = omega_guess_list[0]
        phi = phase_raman_pulse_start - omega0*t
        delta_omega0 = omega0 - omega_raman
        (sin_wt, cos_wt) = self.sincos_lut_interp(phi)
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(-domega * t)
        alpha_z_lightshift = self.omega_z_lightshift * dt_z
        if self.read_alpha_lightshift_on:
            alpha_z_lightshift = self.read_alpha_lightshift
        alpha_z = dt_eff * delta_omega0 - alpha_z_lightshift
        (sin_z, cos_z) = self.sincos_lut_interp(alpha_z)
        alpha_z_step = dt_eff * domega
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(alpha_z_step)
        j = 0
        while j < m:
            delta_omega = omega_raman - omega_guess_list[j]
            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H
                x = -dt_ideal * norm_H
                x -= two_pi * int(x * inv_two_pi)
                if x < 0.0:
                    x += two_pi
                y = x * lut_scale
                i0 = int(y) & lut_mask
                frac = y - i0
                i1 = (i0 + 1) & lut_mask
                s0 = sin_lut[i0]
                c0 = sin_lut[(i0 + lut_quarter) & lut_mask]
                sin_H = s0 + frac * (sin_lut[i1] - s0)
                cos_H = c0 + frac * (sin_lut[(i1 + lut_quarter) & lut_mask] - c0)
            else:
                Omega_over_H = 0.0
                u_z = 0.0
                sin_H = 0.0
                cos_H = 1.0
            sx = state_x[j]
            sy = state_y[j]
            sz = state_z[j]
            u_x = Omega_over_H * cos_wt
            u_y = Omega_over_H * sin_wt
            one_minus_cos = 1.0 - cos_H
            uxuy = one_minus_cos * u_x * u_y
            uxuz = one_minus_cos * u_x * u_z
            uyuz = one_minus_cos * u_y * u_z
            hx = (cos_H + one_minus_cos * u_x * u_x) * sx + (uxuy - sin_H * u_z) * sy + (uxuz + sin_H * u_y) * sz
            hy = (uxuy + sin_H * u_z) * sx + (cos_H + one_minus_cos * u_y * u_y) * sy + (uyuz - sin_H * u_x) * sz
            hz = (uxuz - sin_H * u_y) * sx + (uyuz + sin_H * u_x) * sy + (cos_H + one_minus_cos * u_z * u_z) * sz
            nx = cos_z * hx + sin_z * hy
            ny = -sin_z * hx + cos_z * hy
            if twist_on:
                d_twist = twist * hz
                cos_d = 1.0 - d_twist * d_twist * 0.5
                nx_twisted = cos_d * nx + d_twist * ny
                ny = -d_twist * nx + cos_d * ny
                nx = nx_twisted
            coherence = coherence0
            if slope_on:
                coherence = coherence + slope * hz
                if coherence < 0.0:
                    coherence = 0.0
                elif coherence > 1.0:
                    coherence = 1.0
            state_x[j] = nx * coherence
            state_y[j] = ny * coherence
            state_z[j] = hz
            p1 = 0.5 * (1.0 + hz)
            if remap:
                p1 += mid * (1.0 - hz * hz)
            if p1 < 0.0:
                p1 = 0.0
            elif p1 > 1.0:
                p1 = 1.0
            p1s[j] = p1
            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            j += 1

    @portable(flags={"fast-math"})
    def update_with_measurement(self, k, update_raman_frequency=1, update_rabi_frequency=0, include_photon_noise=1):
        P0_total = 0.0
        moment_2 = 0.0
        mn = 0.0
        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        P0 = self.P0
        p1s = self.p1_scratch
        m = self.m
        n_photons = int(self.N_photons_per_shot)
        sigma = self.std_n_photons_per_shot
        c = 0.5 / (sigma * sigma)
        j = 0
        while j < m:
            num = k - n_photons * p1s[j]
            pj = P0[j] * np.exp(-c * num * num)
            P0_total += pj
            mn += pj * omega_guess_list[j]
            P0[j] = pj
            j += 1
        if P0_total <= 0.0:
            uniform = 1.0 / m
            i = 0
            while i < len(P0):
                P0[i] = uniform
                i += 1
            self.P0_total = 1.0
            self._degenerate_posterior_counter += 1
            return self.omega_raman, self.omega_raman, self.Omega
        inv_total = 1.0 / P0_total
        mn = mn * inv_total
        max_idx = 0
        max_prob = -1.0
        i = 0
        while i < len(P0):
            v = P0[i] * inv_total
            P0[i] = v
            if v > max_prob:
                max_prob = v
                max_idx = i
            i += 1
        self.P0_total = P0_total
        omega_max = self.map_frequency(max_idx, max_prob)
        self.max_idx = max_idx
        uniform_prob = 1.0 / m
        if max_prob < 1.15 * uniform_prob:
            omega_raman_out = mn
            self._flat_prob_counter += 1
        else:
            omega_raman_out = omega_max
        self.omega_max = omega_max
        if not update_raman_frequency:
            omega_raman_out = self.omega_raman
        return omega_raman_out, mn, self.Omega

    @kernel
    def hot_stage(self):
        r = self.raman
        rtio_output(r._fw_cfg_target, r._fw_cfg8)
        delay_mu(r._fw_ref_mu)
        rtio_output(r._fw_data_target, r._fw_addr)
        delay_mu(r._fw_xfer8_mu)
        rtio_output(r._fw_cfg_target, r._fw_cfg32)
        delay_mu(r._fw_ref_mu)

    @kernel(flags={"fast-math"})
    def hot_write(self, f):
        r = self.raman
        ftw = r._fw_ref_ftw + int32(round(r._fw_ftw_per_delta * (f - r._ao_ref_delta)))
        r.frequency_transition = f
        r.dds0._last_ftw = r.dds0._ftw
        r.dds1._last_ftw = r.dds1._ftw
        if r._ao_uses0 == 1:
            r._new_ftw0 = ftw
            r._new_ftw1 = r.dds1._ftw
        else:
            r._new_ftw0 = r.dds0._ftw
            r._new_ftw1 = ftw
        rtio_output(r._fw_data_target, ftw)

    @kernel
    def hot_update(self, t_step, dT, chained) -> TFloat:
        # RamanBeamPair.io_update_and_phase_update, the same event and the same integers
        r = self.raman
        T = self.hc_t_io_update_pretrigger_mu
        dt0 = self.hot_dt0
        dt1 = self.hot_dt1
        if chained == 0:
            # chained: the previous step's trace carries this event
            at_mu((t_step - T - self.hc_t_ffu_dds_pipeline_latency) & ~7)
            if r._ao_uses0 == 1:
                delay_mu(dt0)
            else:
                delay_mu(dt1)
            rtio_output(r._fw_io_target, 1)
            delay_mu(int64(8))
            rtio_output(r._fw_io_target, 0)
        r.dds0._ftw = r._new_ftw0
        r.dds1._ftw = r._new_ftw1
        dt0 += int64(4)
        dt1 += int64(4)
        dt = self.hc_t_ffu_pipeline_latency_fudge_mu
        spmu = r._sysclk_per_mu
        r._phi0_mu += r.dds0._last_ftw * (dT - T + dt0 + dt) * spmu >> 16
        r._phi0_mu += r.dds0._ftw * (T - dt0 - dt) * spmu >> 16
        r._phi1_mu += r.dds1._last_ftw * (dT - T + dt1 + dt) * spmu >> 16
        r._phi1_mu += r.dds1._ftw * (T - dt1 - dt) * spmu >> 16
        a0 = r.dds0.aom_order
        a1 = r.dds1.aom_order
        return r.pow_to_phase(2*np.int32(a0*r._phi0_mu - a1*r._phi1_mu))

    @portable(flags={"fast-math"})
    def posterior_std_now(self):
        m1 = 0.0
        m2 = 0.0
        j = 0
        while j < self.m:
            m1 += self.P0[j] * self.omega_guess_list[j]
            m2 += self.P0[j] * self.omega_sq_list[j]
            j += 1
        var = m2 - m1 * m1
        if var < 0.0:
            var = 0.0
        return np.sqrt(var)

    @kernel
    def measurement_overlap(self, i, t, phase_tracker, issue_read, t_next_step, t_pulse_next,
                            preissue, h_full, h_chain):
        """base_expt_feedback.measurement with Sampler_Last_CH.sample_single split: the CNV pulse
        and the SPI write (outputs) are submitted, the measurement-independent half of the
        posterior runs, then the SPI read (the blocking input) and the same decode as sample_single.

        issue_read False = this read's integrator gate + imaging pulse were written in the previous
        step (the cursor jumps to its sample time); preissue True = write the NEXT read's gate +
        imaging pulse now, so no satellite write sits between the ADC read and the next deadline."""
        sampler = self.integrator.sampler_ch.sampler_device
        at_mu(t_next_step)
        if preissue == 1:
            self.core_dma.playback_handle(h_chain)
        else:
            self.core_dma.playback_handle(h_full)

        self.propagate_hypotheses(t, phase_tracker)

        # as Sampler_Last_CH.sample_single for channel 7 only
        val = sampler.bus_adc.read() & 0xffff
        if val & 0x8000:
            val -= 0x10000
        self.data.apd.shot_data[i] = adc_mu_to_volt(val, self.hot_gain, sampler.corrected_fs)
        v = self.convert_measurement(self.data.apd.shot_data[i])
        return v

    @kernel
    def feedback_loop(self, t_start_mu,
                      update_raman_frequency=0,
                      update_rabi_frequency=0,
                      include_photon_noise=1):
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift
        idx = int(self.p.s2_idx)
        arm = int(self.p.s2_tbl_arm[idx])
        fast_row = int(self.p.s2_tbl_fast[idx])
        issued = 0     # 1: the previous step wrote this step's read
        pole_read = int(self.p.s2_tbl_pole_read[idx])
        theta_tomo = self.p.s2_tbl_theta[idx]
        dfreq = self.p.s2_tbl_dfreq[idx]
        steer = self.p.s2_tbl_steer[idx]
        sched = int(self.p.s2_tbl_sched[idx])
        K = int(self.p.s2_tbl_K[idx])
        lad = int(self.p.s2_tbl_lad[idx])
        n_lad = int(self.p.s2_lad_len[lad])
        upd = int(self.p.s2_tbl_update[idx])
        t_max = self.p.s2_t_pulse_max
        t_fallback = self.p.s2_t_pi2
        clamped = 0
        omega_ref = self.omega_raman
        degen0 = self._degenerate_posterior_counter
        self.data.s2_row.put_data(float(idx))
        self.data.s2_fast.put_data(float(fast_row))
        self.data.s2_arm.put_data(float(arm))
        self.data.s2_K.put_data(float(K))
        self.data.s2_lad.put_data(float(lad))
        self.data.s2_steer.put_data(steer)
        self.data.s2_theta.put_data(theta_tomo)
        self.data.s2_dfreq.put_data(dfreq)
        self.data.s2_pole_read.put_data(float(pole_read))
        self.data.s2_sched.put_data(float(sched))
        self.data.s2_shift.put_data(self.p.s2_tbl_shift[idx])
        mode = 0       # 0 stage 1, 1 pole, 2 equator, 3 analysis, 5 tomography, 4 done
        if arm == 4:
            mode = 2
            self.omega_raman += steer * np.pi / (2. * self.p.s2_lad_flat[lad * self.p.s2_Lmax])

        k = 0
        f = self.omega_raman / (2*np.pi)

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        h_full = self.core_dma.get_handle("cf_read")
        h_chain = self.core_dma.get_handle("cf_chain")
        self.imaging.light_guard.ensure_mask_settled()
        sd = self.integrator.sampler_ch.sampler_device
        self.hot_gain = (sd.gains >> (1 + 8 - len(self.integrator.sampler_ch.samples)) * 2) & 0b11
        self.hot_dt0 = int64(self.raman.dds0.dds_device.sync_data.io_update_delay)
        self.hot_dt1 = int64(self.raman.dds1.dds_device.sync_data.io_update_delay)
        at_mu((t_start_mu - 10000) & ~7)

        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.

        dT = self.p.t_between_pulses_mu
        t_turn_on_delay = self.p.t_raman_pulse_offset

        self.data.reinit_pulse.put_data(-1.)
        self.data.reinit_trigger_std.put_data(-1.)
        self.data.reinit_theta.put_data(0.)
        self.data.reinit_sz_pred.put_data(0.)
        self.data.reinit_sz_meas.put_data(0.)
        self.data.reinit_center.put_data(0.)
        self.data.s2_smap_x.put_data(0.)
        self.data.s2_smap_y.put_data(0.)
        self.data.s2_smap_z.put_data(0.)
        self.data.s2_clamped.put_data(0.)
        # a saved aborted shot must not show the previous shot's result
        self.data.s2_n_played.put_data(-1.)
        self.data.s2_final_map.put_data(0.)
        self.data.s2_final_std.put_data(-1.)
        self.data.s2_degenerate.put_data(-1.)
        q = 0
        while q < self.hc_N_pulses:
            self.data.s2_kind.put_data(-1., q)
            self.data.dT_mu.put_data(0., q)
            self.data.apd.put_data(0., q)
            q += 1

        at_mu(t_start_mu)

        n1 = 0
        cyc = 0
        i = 0
        while mode != 4 and i < self.hc_N_pulses:

            f = self.omega_raman / (2*np.pi)
            t_pulse = self.p.t_raman_pulse_list[i]

            self.data.bench_margin.put_data(float(t_step - self.hc_t_raman_set_pretrigger_mu - self.core.get_rtio_counter_mu()), i)
            at_mu(t_step - self.hc_t_raman_set_pretrigger_mu)
            self.hot_write(f)

            t = (t_step - t_start_mu)*1.e-9

            phase_tracker = self.hot_update(t_step, dT, issued)

            do_pulse = 1
            do_read = 1
            sz_pred = 0.
            if mode == 1:
                theta = self.pole_angle(phase_tracker, t)
                sz_pred = self.pole_expected_sz(phase_tracker, t, theta)
                t_pulse = theta / self.Omega + t_turn_on_delay
                if not (t_pulse >= t_turn_on_delay and t_pulse <= t_max):
                    t_pulse = t_fallback
                    clamped += 1
                do_read = pole_read
                self.data.reinit_pulse.put_data(float(i))
                self.data.reinit_theta.put_data(theta)
                self.data.reinit_sz_pred.put_data(sz_pred)
            elif mode == 2:
                t_pulse = self.equator_angle(phase_tracker, t) / self.Omega + t_turn_on_delay
                if not (t_pulse >= t_turn_on_delay and t_pulse <= t_max):
                    t_pulse = t_fallback
                    clamped += 1
                do_read = 0
            elif mode == 3:
                t_pulse = self.p.s2_t_pi2
            elif mode == 5:
                if theta_tomo > 0.:
                    t_pulse = theta_tomo / self.Omega + t_turn_on_delay
                else:
                    do_pulse = 0
                    t_pulse = 0.

            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay

            self.data.bench_margin2.put_data(float(t_step - self.core.get_rtio_counter_mu()), i)
            at_mu(t_step)

            omega_next = self.omega_raman
            if do_pulse == 1:
                if issued == 1:
                    delay(t_pulse)
                    self.raman.dds_sw.dds_device.sw.off()
                else:
                    self.raman.pulse(t_pulse)

            self.data.omega_raman.put_data(self.omega_raman, i)
            self.data.t_raman_pulse.put_data(t_pulse, i)
            self.data.s2_kind.put_data(float(mode), i)
            if i > 0:
                self.data.dT_mu.put_data(float(dT), i - 1)

            # the gap depends only on this step's pulse time, so it is known before the read returns
            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.hc_t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.hc_t_img_pulse,
                t_raman_pretrigger=self.hc_t_raman_set_pretrigger_mu,
                t_fifo_mu=self.hc_t_fifo_mu
            )

            if fast_row == 1 and do_read == 1 and do_pulse == 1:
                # pre-issue only when the next step is a read whatever this read's k: stage 1 with no
                # possible trigger or end. dT then carries the schedule and the clamp before the read.
                preissue = 0
                if mode == 0 and i + 1 < self.hc_N_pulses and self.hc_s2_sched_flat[sched * self.hc_N_pulses + i] == 0.:
                    n1_stop = self.hc_s2_N1
                    if arm == 3:
                        n1_stop = K
                    elif arm == 1 or arm == 2:
                        if self.hc_s2_thr_Omega > 0. and self.hc_s2_K_min < n1_stop:
                            n1_stop = self.hc_s2_K_min
                        elif K < n1_stop:
                            n1_stop = K
                    if n1 + 1 < n1_stop:
                        preissue = 1
                k = self.measurement_overlap(i, t, phase_tracker, 1 - issued, t_step + dT - self.hot_gap_mu + int64(8),
                                             0., preissue, h_full, h_chain)
                if idx & 1 == 1:
                    k = round(self.N_photons_per_shot * self.p1_scratch[self.m // 3])
                issued = preissue
                omega_next, omega_posterior_mean, self.Omega = self.update_with_measurement(k,
                                                            update_raman_frequency=upd,
                                                            update_rabi_frequency=update_rabi_frequency,
                                                            include_photon_noise=include_photon_noise)
            elif do_read == 1:
                k = self.measurement(i)
                if do_pulse == 1:
                    omega_next, omega_posterior_mean, self.Omega = self.generate_posterior(k, t,
                                                            phase_raman_pulse_start=phase_tracker,
                                                            update_raman_frequency=upd,
                                                            update_rabi_frequency=update_rabi_frequency,
                                                            include_photon_noise=include_photon_noise)
            else:
                # no read, so no readout_prepare_sample: stage the next fast frequency update here
                delay(5.e-6)
                self.hot_stage()
                self.rotate_only(t, phase_tracker)

            if mode == 0:
                dT += int64(self.hc_s2_sched_flat[sched * self.hc_N_pulses + i])
                n1 += 1
                fire = 0
                if (arm == 1 or arm == 2) and n1 >= self.hc_s2_K_min:
                    if n1 >= K or (self.hc_s2_thr_Omega > 0. and self.posterior_std_now() < self.hc_s2_thr_Omega * self.Omega):
                        fire = 1
                if arm == 3:
                    if n1 == K - 1:
                        omega_next += 2 * np.pi * dfreq
                    if n1 >= K:
                        mode = 5
                        dT = self.p.s2_tomo_gap_mu
                elif fire == 1:
                    self._posterior_std = self.posterior_std_now()
                    self.data.reinit_trigger_std.put_data(self._posterior_std / self.Omega)
                    mode = 1
                    dT += self.p.s2_extra_pre_mu
                    omega_next += 2 * np.pi * dfreq
                elif n1 >= self.hc_s2_N1:
                    mode = 4
            elif mode == 1:
                if pole_read == 1:
                    self.data.reinit_sz_meas.put_data(2.0 * (k / self.N_photons_per_shot) - 1.0)
                center = self.reinit_to_map()
                self.data.s2_smap_x.put_data(self.s2_sx)
                self.data.s2_smap_y.put_data(self.s2_sy)
                self.data.s2_smap_z.put_data(self.s2_sz)
                self.data.reinit_center.put_data(center)
                omega_next = center
                if arm == 2:
                    mode = 5
                    dT = self.p.s2_tomo_gap_mu
                else:
                    mode = 2
                    dT += self.p.s2_extra_post_mu
                    omega_next = center + steer * np.pi / (2. * self.p.s2_lad_flat[lad * self.p.s2_Lmax])
            elif mode == 2:
                mode = 3
                dT = int64((t_pulse + self.p.s2_lad_flat[lad * self.p.s2_Lmax + cyc]) * 1.e9) & ~7
            elif mode == 3:
                cyc += 1
                if cyc >= n_lad:
                    mode = 4
                else:
                    mode = 2
                    dT += self.p.s2_extra_an_mu
                    omega_next = omega_next + steer * np.pi / (2. * self.p.s2_lad_flat[lad * self.p.s2_Lmax + cyc])
            elif mode == 5:
                mode = 4

            if not (dT > 0 and dT <= self.hc_s2_dT_max_mu):
                dT = self.hc_s2_dT_max_mu
                clamped += 1

            if not (omega_next > omega_ref - self.hc_s2_omega_guard and omega_next < omega_ref + self.hc_s2_omega_guard):
                omega_next = self.omega_raman
                clamped += 1
            self.omega_raman = omega_next


            t_step += dT
            i += 1

        if i > 0:
            self.data.dT_mu.put_data(float(dT), i - 1)
            self.per_feedback_loop_end(idx=i - 1)
        # unplayed rows of the per-pulse containers hold the previous shot: score from these, not from the last row (reviewer K3)
        self.data.s2_n_played.put_data(float(i))
        self.data.s2_final_map.put_data(self.omega_max)
        self._posterior_std = self.posterior_std_now()
        self.data.s2_final_std.put_data(self._posterior_std)
        self.data.s2_clamped.put_data(float(clamped))
        self.data.s2_degenerate.put_data(float(self._degenerate_posterior_counter - degen0))
        self.per_scan_kernel_end()

    @kernel
    def scan_kernel(self):
        self.core.wait_until_mu(now_mu())
        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)
        t_raman_pulse_seed = self.resolve_t_raman_pulse_seed()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(seed=t_raman_pulse_seed)
        self.data.t_raman_pulse_seed.put_data(float(t_raman_pulse_seed))
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.core.break_realtime()

        self.power_down_cooling()
        self.integrator.init()
        sd = self.integrator.sampler_ch.sampler_device
        sd.bus_adc.set_config_mu(SPI_CONFIG | spi.SPI_INPUT | spi.SPI_END, 16, sd.div, SPI_CS_ADC)
        delay(10.e-6)
        self.initialize_feedback()
        delay(10.e-3)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)
        # prep_raman without the shutter: no atoms, and 1000 shots would cycle it hard
        self.raman.init(self.omega_raman/(2*np.pi), self.p.fraction_power_raman, 0., 0., np.int64(-1), 0)
        self.raman.pulse(3.e-3) # warm up
        delay(3.01e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        t_pulse_start_mu = now_mu() + 500000
        self.raman.set_up_fast_frequency_update(aggressive_mode=1)
        at_mu(t_pulse_start_mu - 20000)
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu,
                           update_raman_frequency=self.p.update_raman_frequency_bool,
                           update_rabi_frequency=0,
                           include_photon_noise=self.p.include_photon_noise)

        delay(1.e-3)
        sd.bus_adc.set_config_mu(SPI_CONFIG | spi.SPI_INPUT | spi.SPI_END, 32, sd.div, SPI_CS_ADC)
        delay(10.e-6)
        self.raman.clean_up_fast_frequency_update()
        self.core.wait_until_mu(now_mu())
        self.reset_initial_omega_from_params()
        delay(500.e-3) # keeps the 3 ms warm pulse at the duty of a real shot

    @kernel
    def record_read_events(self):
        sampler = self.integrator.sampler_ch.sampler_device
        t_r0 = now_mu()
        self.integrator.begin_integrate(reset=False)
        self.imaging.dds_sw.on()
        delay(self.p.t_img_pulse)
        self.imaging.dds_sw.off()
        self.integrator.stop_and_settle()
        t0 = now_mu()
        self.cf_off = t0 - t_r0
        at_mu(t0 + 80)
        self.integrator.clear(t=0)
        at_mu(t0)
        sampler.cnv.pulse(30.e-9)
        delay(450.e-9)
        sampler.bus_adc.write(0)
        self.hot_stage()

    @kernel
    def dma_record_read(self):
        # read and sample as one trace, once per run, before the scan
        self.core.break_realtime()
        with self.core_dma.record("cf_read"):
            self.record_read_events()
        self.core.break_realtime()
        delay(1.e-3)
        r = self.raman
        G = self.hot_gap_mu - int64(8)
        t_io = (G - self.p.t_io_update_pretrigger_mu - self.hc_t_ffu_dds_pipeline_latency) & ~7
        d0 = int64(r.dds0.dds_device.sync_data.io_update_delay)
        d1 = int64(r.dds1.dds_device.sync_data.io_update_delay)
        if r._ao_uses0 == 1:
            t_io += d0
        else:
            t_io += d1
        with self.core_dma.record("cf_chain"):
            t_r0 = now_mu()
            self.record_read_events()
            at_mu(t_r0 + t_io)
            rtio_output(r._fw_io_target, 1)
            delay_mu(int64(8))
            rtio_output(r._fw_io_target, 0)
            at_mu(t_r0 + G)
            r.dds_sw.dds_device.sw.on()
        self.core.break_realtime()
        delay(10.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.dma_record_read()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
