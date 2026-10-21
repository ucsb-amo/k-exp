from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
from kexp.util.artiq.async_print import aprint
import numpy as np

class tweezer_pid2_vs_pid1(EnvExperiment, Base):
    """Calibrates the tweezer PID2 photodiode against the PID1 setpoint
    (kexp.calibrations.tweezer: vpd2_per_vpd1_slope, v_pd2_y_intercept).

    No atoms. The tweezer is held by the PID1 (high-power) servo, PID2
    disabled with AO2 on (as between shots), and both servo photodiodes are
    read on the Sampler (ch0 PID1 PD, ch1 PID2 PD), each reading the mean of
    N_tweezer_pid_cal_samples conversions after t_tweezer_pid_cal_settle.

    1. Search (in run(), before the scan, tweezer on throughout): the PID1
       setpoint steps up from v_pd_tweezer_pid1_cal_min in coarse steps until
       a PID2 PD sample reaches v_pid2_pd_saturation (or the setpoint passes
       v_pd_tweezer_pid1_cal_search_max), then in fine steps from the last
       unsaturated setpoint. The highest setpoint with every PID2 sample below
       the threshold is the sweep top, v_pid1_top. PID2 need not saturate: if
       it does not, the sweep top is the cap. The trace is saved (search_*
       containers, the same in every shot; -1 = step not taken).
    2. Sweep (the scan, one shot per point): setpoint = min + frac_pid1_sweep *
       (v_pid1_top - min), frac_pid1_sweep from 1 down to 0 in order (not
       shuffled), each shot tweezer on -> setpoint -> settle -> read -> off.

    analyze() fits PID2 PD vs PID1 setpoint (kexp.analysis.tweezer_pid_calibration)
    and, when no flag is raised and write_back_tweezer_cal is True, writes the
    slope and intercept into kexp/calibrations/tweezer.py (old lines commented
    out, new ones tagged with the run id and date; never committed).
    WAXX_CAL_NO_WRITE_BACK=1 vetoes the write.

    End state. Normal finish: tweezer off (AO1 off, rf sw off, PID1 setpoint
    0 V, PID1 integrator held), PID2 disabled with AO2 on (its idle state),
    AWG reset by post_scan. Any exception out of the search or the scan
    (an underflow, the liveOD Abort, anything else): run()'s handler turns the
    tweezer off the same way, then re-raises. No coils, shutters or other
    beams are used. The highest power reached is PID1 =
    v_pd_tweezer_pid1_cal_search_max (0.4 V; HF loading ramps to 8.4 V).
    """

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      save_data=True,
                      diagnostic_images=False,
                      warmup_shots=3)

        # the calibration this run starts with (analysis refuses to write if
        # the file changed during the run)
        import kexp.calibrations.tweezer as tweezer_cal
        self.p.vpd2_per_vpd1_slope_at_start = tweezer_cal.vpd2_per_vpd1_slope
        self.p.v_pd2_y_intercept_at_start = tweezer_cal.v_pd2_y_intercept

        self.p.v_pd_tweezer_pid1_cal_min = 0.08
        self.p.v_pd_tweezer_pid1_cal_search_max = 0.4
        self.p.dv_pd_tweezer_pid1_cal_coarse = 5.e-3
        self.p.dv_pd_tweezer_pid1_cal_fine = 0.5e-3
        self.p.v_pid2_pd_saturation = 10.
        self.p.t_tweezer_pid_cal_settle = 20.e-3
        self.p.N_tweezer_pid_cal_samples = 50

        # paint as in the evaporation (at v_hf_tweezer_paint_amp_max)?
        self.paint_tweezer = False

        self.write_back_tweezer_cal = True

        self.p.frac_pid1_sweep = 1.
        self.xvar('frac_pid1_sweep', np.linspace(1., 0., 15))
        self.p.N_repeats = 3

        # search bookkeeping (kernel attributes)
        span = self.p.v_pd_tweezer_pid1_cal_search_max - self.p.v_pd_tweezer_pid1_cal_min
        self._n_coarse = int(np.floor(span / self.p.dv_pd_tweezer_pid1_cal_coarse + 1.e-9)) + 1
        self._n_fine = int(round(self.p.dv_pd_tweezer_pid1_cal_coarse / self.p.dv_pd_tweezer_pid1_cal_fine))
        self._n_search_max = self._n_coarse + self._n_fine
        self.v_pid1_top = self.p.v_pd_tweezer_pid1_cal_min
        self._sat_found = 0
        self._sat_at_min = 0
        # (PID1 mean, PID1 std, PID2 mean, PID2 std, PID2 max) of one reading
        self._meas = np.zeros(5)

        # per shot (the sweep)
        self.data.v_pid1_setpoint = self.data.add_data_container(1, np.float64)
        self.data.v_pid1_pd = self.data.add_data_container(1, np.float64)
        self.data.v_pid1_pd_std = self.data.add_data_container(1, np.float64)
        self.data.v_pid2_pd = self.data.add_data_container(1, np.float64)
        self.data.v_pid2_pd_std = self.data.add_data_container(1, np.float64)
        self.data.v_pid2_pd_max = self.data.add_data_container(1, np.float64)
        # the search (the same in every shot)
        self.data.v_pid1_top = self.data.add_data_container(1, np.float64)
        self.data.pid2_saturation_found = self.data.add_data_container(1, np.int32)
        self.data.pid2_saturated_at_min = self.data.add_data_container(1, np.int32)
        self.data.search_v_pid1 = self.data.add_data_container(self._n_search_max, np.float64)
        self.data.search_v_pid1_pd = self.data.add_data_container(self._n_search_max, np.float64)
        self.data.search_v_pid2_pd = self.data.add_data_container(self._n_search_max, np.float64)
        self.data.search_v_pid2_pd_max = self.data.add_data_container(self._n_search_max, np.float64)

        self.finish_prepare(shuffle=False)

    @kernel
    def measure_pds(self, v_pid1):
        """PID1 setpoint to v_pid1, settle, then the mean / std of both PDs
        and the PID2 maximum over N_tweezer_pid_cal_samples reads (into
        self._meas). Ends with the timeline in the future (break_realtime)."""
        self.tweezer.set_power(v_pd=v_pid1)
        delay(self.p.t_tweezer_pid_cal_settle)
        n = self.p.N_tweezer_pid_cal_samples
        s1 = 0.
        q1 = 0.
        s2 = 0.
        q2 = 0.
        m2 = -1.e9
        for i in range(n):
            # a Sampler read blocks until its timestamp: room for the next one
            self.core.break_realtime()
            v1, v2 = self.tweezer.read_pds()
            s1 += v1
            q1 += v1 * v1
            s2 += v2
            q2 += v2 * v2
            if v2 > m2:
                m2 = v2
        self.core.break_realtime()
        mean1 = s1 / n
        mean2 = s2 / n
        self._meas[0] = mean1
        self._meas[1] = self.sample_std(q1, mean1, n)
        self._meas[2] = mean2
        self._meas[3] = self.sample_std(q2, mean2, n)
        self._meas[4] = m2

    @portable
    def sample_std(self, sum_sq, mean, n) -> TFloat:
        if n < 2:
            return 0.
        var = (sum_sq - n * mean * mean) / (n - 1)
        if var < 0.:
            var = 0.
        return var ** 0.5

    @kernel
    def record_search_step(self, i, v):
        if i < self._n_search_max:
            self.data.search_v_pid1.put_data(v, i)
            self.data.search_v_pid1_pd.put_data(self._meas[0], i)
            self.data.search_v_pid2_pd.put_data(self._meas[2], i)
            self.data.search_v_pid2_pd_max.put_data(self._meas[4], i)

    @kernel
    def find_pid2_saturation(self):
        """The search (see the class docstring). Sets v_pid1_top,
        _sat_found, _sat_at_min. The tweezer must be on."""
        for i in range(self._n_search_max):
            self.data.search_v_pid1.put_data(-1., i)
            self.data.search_v_pid1_pd.put_data(-1., i)
            self.data.search_v_pid2_pd.put_data(-1., i)
            self.data.search_v_pid2_pd_max.put_data(-1., i)

        v_min = self.p.v_pd_tweezer_pid1_cal_min
        v_cap = self.p.v_pd_tweezer_pid1_cal_search_max
        thr = self.p.v_pid2_pd_saturation
        v_good = -1.
        v_bad = -1.
        i = 0
        for k in range(self._n_coarse):
            v = v_min + k * self.p.dv_pd_tweezer_pid1_cal_coarse
            if v > v_cap:
                break
            self.measure_pds(v)
            self.record_search_step(i, v)
            i += 1
            if self._meas[4] >= thr:
                v_bad = v
                break
            v_good = v

        if v_bad > 0. and v_good > 0.:
            v0 = v_good
            for k in range(1, self._n_fine):
                v = v0 + k * self.p.dv_pd_tweezer_pid1_cal_fine
                if v >= v_bad:
                    break
                self.measure_pds(v)
                self.record_search_step(i, v)
                i += 1
                if self._meas[4] >= thr:
                    v_bad = v
                    break
                v_good = v

        if v_good > 0.:
            self.v_pid1_top = v_good
            self._sat_at_min = 0
        else:
            self.v_pid1_top = v_min
            self._sat_at_min = 1
        self._sat_found = 1 if v_bad > 0. else 0

        if self._sat_at_min == 1:
            aprint("[pid cal] PID2 PD saturated already at the minimum setpoint", v_min,
                   "V: there is nothing unsaturated to sweep.")
        elif self._sat_found == 1:
            aprint("[pid cal] PID2 PD saturates at PID1 =", v_bad,
                   "V; sweep top (highest unsaturated) =", self.v_pid1_top, "V")
        else:
            aprint("[pid cal] no PID2 saturation up to the cap; sweep top = cap =",
                   self.v_pid1_top, "V")

    @kernel
    def warmup_kernel(self):
        # tweezer light only (the default warm-up is the full hf tweezer sequence)
        self.tweezer.on(paint=self.paint_tweezer)
        self.tweezer.set_power(v_pd=self.p.v_pd_tweezer_pid1_cal_min)
        delay(self.p.t_tweezer_pid_cal_settle)
        self.tweezer.off()

    @kernel
    def scan_kernel(self):
        v_min = self.p.v_pd_tweezer_pid1_cal_min
        v = v_min + self.p.frac_pid1_sweep * (self.v_pid1_top - v_min)

        self.tweezer.on(paint=self.paint_tweezer)
        self.measure_pds(v)
        self.tweezer.off()

        self.data.v_pid1_setpoint.put_data(v)
        self.data.v_pid1_pd.put_data(self._meas[0])
        self.data.v_pid1_pd_std.put_data(self._meas[1])
        self.data.v_pid2_pd.put_data(self._meas[2])
        self.data.v_pid2_pd_std.put_data(self._meas[3])
        self.data.v_pid2_pd_max.put_data(self._meas[4])
        self.data.v_pid1_top.put_data(self.v_pid1_top)
        self.data.pid2_saturation_found.put_data(self._sat_found)
        self.data.pid2_saturated_at_min.put_data(self._sat_at_min)

    @kernel
    def run(self):
        self.init_kernel()
        self.core.break_realtime()
        self.reset_tweezers(False)   # AWG traps loaded + triggered (light needs them)
        self.core.break_realtime()
        try:
            self.tweezer.on(paint=self.paint_tweezer)
            self.find_pid2_saturation()
            self.tweezer.off()
            self.scan()
        except:
            self.core.break_realtime()
            self.tweezer.off()
            raise

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
        if not self.run_info.save_data:
            return
        try:
            from kexp.analysis.tweezer_pid_calibration import calibrate_run
            calibrate_run(self.run_info.run_id, write_back=self.write_back_tweezer_cal)
        except Exception as e:
            print(f"[tweezer pid cal] analysis failed ({e!r}); the run is saved. Redo with "
                  f"kexp.analysis.tweezer_pid_calibration.calibrate_run({self.run_info.run_id}, "
                  f"write_back=True).")
