"""Run a feedback experiment's real feedback_loop on the host and record its RTIO events.

Not a test by itself (test_fastpath_rtio_stream.py uses it). The experiment is prepared
against the real device db with every network client stubbed (as
test_feedback_subscan_compiles.py), so the waxx wrappers and ARTIQ's own drivers are the
real ones. Only the bottom is replaced:

  * a time manager keeps the timeline cursor (at_mu may go back, as on the core device);
  * rtio_output records (write order, timestamp, target, data);
  * rtio_input_data serves the ADC words of a read list, in order.

No core-device connection is made: core.run is replaced before any kernel is called, so
an @kernel method is a plain Python call. No UDP, no liveOD, nothing written outside
pytest's temp dir.

What this can and cannot show: it is the true event stream of the code as written, down
to the DDS SPI words; it is not the compiled kernel, so CPU time (and with it underflows)
and the compiler's float rounding are out of reach -- those are the on-hardware steps.
"""
import os
from collections import namedtuple
from types import SimpleNamespace

import numpy as np

Event = namedtuple("Event", "seq t target data")

# as the 2026-10-29 / 30 overnight files (fbna_FB_c7s0.py), which ran the standard path
NARROW_GRID = dict(N_pulses=11, feedback_grid_size=21, frequency_feedback_grid_full_span=8844.4,
                   slack_mu=39696, update_raman_frequency_bool=1, include_photon_noise=1)

EXPT = '''
from artiq.experiment import *
from BASE_IMPORT
import numpy as np
from numpy import int64

class HostStream(EnvExperiment, FeedbackExpt):
    def prepare(self):
        FeedbackExpt.__init__(self, save_data=False, suppress_live_od=True, recalibrate=False)
        self.p.update_raman_frequency_bool = UPDATE
        self.p.include_photon_noise = 1
        self.p.N_warmup_shots = 0
        self.p.N_pulses = N_PULSES
        self.p.N_repeats = 1
        self.p.t_calculation_slack_compensation_mu = int64(SLACK_MU)
        self.p.feedback_grid_size = GRID_SIZE
        self.p.frequency_feedback_grid_full_span = FULL_SPAN
        self.p.feedback_fractional_initial_offset = OFFSET
        self.xvar('feedback_grid_shift', np.array([0.0]))
        self.finish_prepare(shuffle=False)
'''

STD_IMPORT = "kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt"
FAST_IMPORT = ("kexp.experiments.HF_experiments.feedback.alias_grid.base_expt_feedback_fast "
               "import FeedbackExptFast as FeedbackExpt")


class HostTime:
    """The timeline cursor, in mu. Sequential blocks as artiq.sim.time, but at_mu may rewind
    (the kernels do, on purpose) and there is no global ordering check: that is the point."""

    def __init__(self, ref_period=1e-9):
        self.ref_period = ref_period
        self.stack = [SimpleNamespace(now=0, parallel=False, longest=0)]
        self.on_parallel_end = lambda: None

    def enter_sequential(self):
        self.stack.append(SimpleNamespace(now=self.get_time_mu(), parallel=False, longest=0))

    def enter_parallel(self):
        self.stack.append(SimpleNamespace(now=self.get_time_mu(), parallel=True, longest=0))

    def exit(self):
        old = self.stack.pop()
        if old.parallel:
            self.set_time_mu(old.now + old.longest)
        else:
            self.set_time_mu(old.now)
        if not self.in_parallel():
            self.on_parallel_end()

    def in_parallel(self):
        return any(c.parallel for c in self.stack)

    def get_time_mu(self):
        return self.stack[-1].now

    def set_time_mu(self, t):
        top = self.stack[-1]
        if top.parallel:
            top.longest = max(top.longest, int(t) - top.now)
        else:
            top.now = int(t)

    def take_time_mu(self, duration):
        self.set_time_mu(self.get_time_mu() + int(duration))

    def take_time(self, duration):
        # the compiler's delay(t): round(t / ref_period)
        self.take_time_mu(round(duration / self.ref_period))


class HostCore:
    """What an @kernel wrapper needs from `self.core` on an object that has none. A kernel
    function called inside `with parallel` is one branch: its own statements are sequential,
    so a call opens a sequential block there (without it each of its delays would start from
    the top of the parallel block)."""

    def __init__(self, clock):
        self.clock = clock

    def run(self, k_function, k_args, k_kwargs):
        if not self.clock.stack[-1].parallel:
            return k_function.artiq_embedded.function(*k_args, **k_kwargs)
        self.clock.enter_sequential()
        try:
            return k_function.artiq_embedded.function(*k_args, **k_kwargs)
        finally:
            self.clock.exit()


def encode_adc_word(volts, sampler, ch):
    """The 32-bit SPI word whose decode (Sampler_Last_CH.sample_single_mu) gives `volts` on
    `ch`: the inverse of adc_mu_to_volt at this channel's gain."""
    from artiq.coredevice.sampler import adc_mu_to_volt
    channel = (ch - 6) + 8 - 8
    gain = (sampler.gains >> channel * 2) & 0b11
    per_mu = adc_mu_to_volt(1000, gain, sampler.corrected_fs) / 1000.
    mu = int(round(volts / per_mu))
    other = 0
    d0, d1 = (mu, other) if ch == 6 else (other, mu)
    word = ((d1 & 0xffff) << 16) | (d0 & 0xffff)
    # TInt32 on the core device: `val >> 16` in the decode sign-extends
    return word - (1 << 32) if word >= (1 << 31) else word


def _give_host_core(root, core, depth=5, seen=None):
    """Every object reachable from `root` that runs @kernel methods gets a core: the real
    drivers keep theirs (its run is replaced), the waxx wrappers have none."""
    seen = set() if seen is None else seen
    if id(root) in seen or depth == 0:
        return
    seen.add(id(root))
    try:
        attrs = vars(root)
    except TypeError:
        return
    mod = type(root).__module__ or ""
    if mod.split(".")[0] in ("waxx", "kexp") and ("core" not in attrs or isinstance(attrs["core"], HostCore)):
        try:
            root.core = core
        except AttributeError:
            pass
    for v in list(attrs.values()):
        if isinstance(v, (list, tuple)):
            for x in v:
                if (type(x).__module__ or "").split(".")[0] in ("waxx", "kexp", "artiq"):
                    _give_host_core(x, core, depth - 1, seen)
        elif (type(v).__module__ or "").split(".")[0] in ("waxx", "kexp", "artiq"):
            _give_host_core(v, core, depth - 1, seen)


def build(monkeypatch, tmp_path, fast, slack_mu=NARROW_GRID["slack_mu"], offset=0.0,
          update=NARROW_GRID["update_raman_frequency_bool"], n_pulses=NARROW_GRID["N_pulses"],
          grid_size=NARROW_GRID["feedback_grid_size"],
          full_span=NARROW_GRID["frequency_feedback_grid_full_span"]):
    import test_feedback_subscan_compiles as sub
    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.language.environment import ProcessArgumentManager
    from artiq.tools import file_import, get_experiment
    from waxx.base import monitor as wmon
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id
    import waxx.control.misc.oscilloscopes as osc
    from waxx.control.slm.slm import SLM

    state = str(tmp_path / "device_state.json")
    monkeypatch.setattr(wmon, "MonitorClient", sub._StubServerClient)
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=state))
    monkeypatch.setattr(kclients, "APDStageClient",
                        lambda *a, **k: SimpleNamespace(set_apd_stage=lambda *a, **k: None))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))
    monkeypatch.setattr(SLM, "reinit_if_due", lambda self, **kw: {"result": "host", "by": kw.get("by")})
    monkeypatch.setattr(osc, "SiglentSDS2000X_Base", sub._StubScope)

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            raise RuntimeError("host stream: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)

    text = (EXPT.replace("BASE_IMPORT", FAST_IMPORT if fast else STD_IMPORT)
            .replace("UPDATE", str(int(update))).replace("N_PULSES", str(n_pulses))
            .replace("SLACK_MU", str(int(slack_mu))).replace("GRID_SIZE", str(grid_size))
            .replace("FULL_SPAN", repr(float(full_span))).replace("OFFSET", repr(float(offset))))
    path = tmp_path / f"host_stream_{int(fast)}_{slack_mu}.py"
    path.write_text(text)
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="host_stream_")
    cls = get_experiment(module)
    exp = cls((device_mgr, sub._NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return exp, device_mgr


def run_train(monkeypatch, exp, reads_v, t_start_mu=10_000_000, slack_mu=None, offset=None,
              update=None):
    """One shot's train: feedback_loop as scan_kernel calls it, from fresh posterior state,
    with the APD reading reads_v[i] at read i. slack_mu / offset / update override the
    prepared values for this train. Returns (events, result)."""
    import artiq.language.core as lang
    import artiq.coredevice.spi2 as spi2
    import artiq.coredevice.ttl as ttl

    clock = HostTime()
    lang.set_time_manager(clock)
    events = []

    # On the core device the compiler interleaves `with parallel` branches in time order; run
    # here one after the other they would look like rewinds that never happen. Hold a parallel
    # block's writes and release them sorted by timestamp when it ends.
    held = []

    def rtio_output(target, data):
        if clock.in_parallel():
            held.append((clock.get_time_mu(), int(target), int(data)))
        else:
            events.append(Event(len(events), clock.get_time_mu(), int(target), int(data)))

    def release_held():
        for t, target, data in sorted(held, key=lambda x: x[0]):
            events.append(Event(len(events), t, target, data))
        held.clear()

    clock.on_parallel_end = release_held

    sampler = exp.integrator.sampler_ch.sampler_device
    ch = exp.integrator.sampler_ch.ch
    words = [encode_adc_word(v, sampler, ch) for v in reads_v]
    read_order = []
    adc_channel = sampler.bus_adc.channel

    def rtio_input_data(channel):
        if channel != adc_channel:
            raise RuntimeError(f"unexpected input on channel {channel}")
        i = len(read_order)
        # a read must find its conversion already submitted: the word is served only if an
        # SPI data write on the ADC bus has been issued for it
        n_writes = sum(1 for e in events
                       if (e.target >> 8) == adc_channel and (e.target & 0xff) == spi2.SPI_DATA_ADDR)
        if n_writes <= i:
            raise RuntimeError(f"ADC read {i} before its conversion was submitted")
        read_order.append(clock.get_time_mu())
        return words[i]

    monkeypatch.setattr(spi2, "rtio_output", rtio_output)
    monkeypatch.setattr(ttl, "rtio_output", rtio_output)
    from waxx.control import raman_beams
    monkeypatch.setattr(raman_beams, "rtio_output", rtio_output)
    monkeypatch.setattr(spi2, "rtio_input_data", rtio_input_data)

    host_core = HostCore(clock)
    monkeypatch.setattr(exp.core, "run", host_core.run)
    monkeypatch.setattr(exp.core, "get_rtio_counter_mu",
                        lambda: clock.get_time_mu() - 10**12, raising=False)
    _give_host_core(exp, host_core)

    if slack_mu is not None:
        exp.p.t_calculation_slack_compensation_mu = np.int64(slack_mu)
    if offset is not None:
        exp.p.feedback_fractional_initial_offset = float(offset)
        exp.p.compute_feedback_grid()
    if update is not None:
        exp.p.update_raman_frequency_bool = int(update)

    # scan_kernel's state at the top of the train, without its hardware preparation
    exp.omega_raman = exp.reset_initial_omega_from_params()
    exp.p.t_between_pulses_mu = exp.compute_t_between_pulses_mu(
        t_calculation_slack_compensation_mu=exp.p.t_calculation_slack_compensation_mu,
        t_raman_pulse=exp.p.t_raman_pulse, t_img_pulse=exp.p.t_img_pulse,
        t_raman_pretrigger=exp.p.t_raman_set_pretrigger_mu, t_fifo_mu=exp.p.t_fifo_mu)
    exp.reset_feedback_state()
    exp._initialize_frequency_grid()
    exp.p.omega_pulse_list = exp.get_new_pulse_list(seed=exp.p.pulse_list_seed)
    exp.p.t_raman_pulse_list = exp.get_new_t_raman_pulse_list(seed=exp.resolve_t_raman_pulse_seed())
    exp.omega_raman = exp.reset_initial_omega_from_params()
    for name in ("omega_raman", "apd", "t", "s_z"):
        getattr(exp.data, name).shot_data[...] = 0.

    clock.set_time_mu(t_start_mu - 20_000)
    exp.raman.set_up_fast_frequency_update(aggressive_mode=1)
    n_setup = len(events)
    exp.feedback_loop(t_start_mu=t_start_mu, update_raman_frequency=exp.p.update_raman_frequency_bool,
                      update_rabi_frequency=0, include_photon_noise=exp.p.include_photon_noise)
    t_end = clock.get_time_mu()
    exp.raman.clean_up_fast_frequency_update()
    result = SimpleNamespace(
        t_end=t_end, n_setup=n_setup, n_reads=len(read_order),
        P0=np.array(exp.P0, dtype=float), omega_raman=float(exp.omega_raman),
        omega_drives=np.array(exp.data.omega_raman.shot_data, dtype=float),
        apd=np.array(exp.data.apd.shot_data, dtype=float),
        t=np.array(exp.data.t.shot_data, dtype=float),
        s_z=np.array(exp.data.s_z.shot_data, dtype=float),
        t_pulses=np.array(exp.p.t_raman_pulse_list, dtype=float))
    return events, result


def lane_model(events, lanes=8, coarse_mu=8, compensation=None):
    """Sequence errors the writes in this order would raise, per the SED lane distributor
    (artiq/gateware/rtio/sed/lane_distributor.py), per DRTIO destination.

    Each destination has its own SED. A write whose (coarse, compensated) timestamp is above
    the last one stays in the current lane, otherwise it moves to the next lane; either way it
    must be above that lane's last timestamp, else it is a sequence error -- reported only in
    the core log, and the event is not played. Lane spreading (lanes also advance when full)
    and the per-channel compensation are not modelled (0 unless given): this is a screen, the
    core log after a real run is the test.

    Returns dict(n_events, n_lane_switches, n_sequence_errors, first_errors, n_rewinds,
    max_rewind_mu).
    """
    state = {}
    out = dict(n_events=len(events), n_lane_switches=0, n_sequence_errors=0, first_errors=[],
               n_rewinds=0, max_rewind_mu=0)
    last_t = {}
    for e in events:
        ch = e.target >> 8
        dest = ch >> 16
        comp = 0 if compensation is None else compensation.get(ch, 0)
        ts = (e.t + comp) // coarse_mu
        s = state.setdefault(dest, dict(lane=0, last=-(10**18), lanes=[-(10**18)] * lanes))
        if dest in last_t and e.t < last_t[dest]:
            out["n_rewinds"] += 1
            out["max_rewind_mu"] = max(out["max_rewind_mu"], last_t[dest] - e.t)
        last_t[dest] = e.t
        use = s["lane"] if ts > s["last"] else (s["lane"] + 1) % lanes
        if use != s["lane"]:
            out["n_lane_switches"] += 1
        if ts > s["lanes"][use]:
            s["lane"], s["last"] = use, ts
            s["lanes"][use] = ts
        else:
            out["n_sequence_errors"] += 1
            if len(out["first_errors"]) < 5:
                out["first_errors"].append(e)
    return out
