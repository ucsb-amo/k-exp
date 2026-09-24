"""OPXManager -- the experiment-facing handle (Base assigns self.opx).

Lifecycle against the experiment:

    prepare():           self.opx.use(sequence)      # registers containers
    finish_prepare():    -> on_finish_prepare()      # tables, trace, compile,
                                                     #   execute (job parks on
                                                     #   its first trigger)
    scan_kernel():       handoff_to_quantum_machines() /
                         wait_for_quantum_machines_handback()  (control.py)
    analyze() -> end():  -> finish()                 # fetch streams into the
                                                     #   containers, halt

Constructed inert and host-only: nothing imports qm until use(), so kexp
imports cleanly on machines without qm-qua installed, and ARTIQ kernel
compilation never sees it.

Data integrity on incomplete runs (abort, underflow with save opted in):
shots the OPX never ran are NaN, an opx_data_valid mask container (0/1,
unshuffled with everything else) records exactly which shots carry real
data, and the completed/expected counts are printed and never inferred.

Generic (future waxx.control.opx): no kexp imports -- the lab wires host,
cluster, channel map and config through the factory in opx_config.py.
"""

import atexit
import logging
import time
from typing import TYPE_CHECKING, Optional

import numpy as np

from waxx.util import console

if TYPE_CHECKING:
    # static-analysis only -- qm must not import at runtime until use()
    from qm import QuantumMachinesManager
    from qm.quantum_machine import QuantumMachine
    from qm.jobs.running_qm_job import RunningQmJob
    from qm.jobs.simulated_job import SimulatedJob

from kexp.control.opx.sequence import get_sequence
from kexp.control.opx.params_bridge import (build_shot_tables, ShotTables,
                                            derived_dependents)
from kexp.control.opx.builder import OPXProgramBuilder
from kexp.control.opx.units import demod2volts

VALID_MASK_KEY = 'opx_data_valid'
QUA_SOURCE_ATTR = 'opx_qua_program'


def _qm_log_gate(record):
    """Logging filter on the ``qm`` logger. qm-qua attaches its own stdout
    handler at INFO on import (importing it already prints a session line),
    so its chatter is gated by the run's verbosity instead: INFO passes only
    at console.VERBOSE, warnings and errors always pass. The verbosity is
    read at log time, so the flag controls an already-imported qm too."""
    if record.levelno >= logging.WARNING:
        return True
    return console.get_level() >= console.VERBOSE


_qm_log_gate_installed = False


def check_live_adjust_conflicts(expt, tables):
    """Refuse a run whose liveOD Adjust panel could change a parameter the
    OPX program depends on.

    The OPX program is baked from the per-shot tables at finish_prepare; the
    Adjust panel changes host params between shots. A parameter the sequence
    read through ctx.p -- directly, or through a derived quantity that
    follows it -- must therefore not be adjustable, or ARTIQ and the OPX
    would silently run different values. Scan it as an xvar instead.
    """
    specs = getattr(expt, '_adjust_specs', None) or []
    accessed = sorted(tables.accessed)
    if not specs or not accessed:
        return
    for spec in specs:
        key = spec.key
        if key in accessed:
            raise RuntimeError(
                f"[opx] {key!r} is registered with adjust() but the OPX "
                f"sequence reads ctx.p.{key}: the OPX baked its per-shot "
                f"values at finish_prepare and would not follow the Adjust "
                f"panel. Drop the adjust() or scan it as an xvar.")
        dependents = derived_dependents(expt, key, accessed)
        if dependents:
            raise RuntimeError(
                f"[opx] {key!r} is registered with adjust() and the OPX "
                f"sequence reads {dependents}, which derive from it: the OPX "
                f"baked those per-shot values at finish_prepare and would "
                f"not follow the Adjust panel. Drop the adjust() or scan it "
                f"as an xvar.")


def _install_qm_log_gate():
    """Install ``_qm_log_gate`` on the ``qm`` logger, once per process.
    Must run BEFORE the first ``import qm``: filters on the logger survive
    qm's own ``config_loggers`` (which resets the level and adds the
    handler), so this also catches the import-time "Starting session"
    line."""
    global _qm_log_gate_installed
    if _qm_log_gate_installed:
        return
    logging.getLogger("qm").addFilter(_qm_log_gate)
    _qm_log_gate_installed = True


class OPXManager:

    def __init__(self, expt, host=None, cluster=None,
                 map_builder=None, config_builder=None):
        self._expt = expt
        self._host = host
        self._cluster = cluster
        self._map_builder = map_builder
        self._config_builder = config_builder

        self._sequence = None
        self._simulate = False
        self._simulate_duration = 200.e-6
        self._simulate_shots = 1
        self._simulate_web_plot = True
        self._map = None
        self._qmm: 'Optional[QuantumMachinesManager]' = None
        self._qm: 'Optional[QuantumMachine]' = None
        self._job: 'Optional[RunningQmJob]' = None
        self._n_shots = 0
        self._stream_roles = {}
        self._finished = False
        self._atexit_registered = False

        # simulation results land here (see _run_simulation); interactive
        # drivers (OPXBench) set _exit_after_simulate = False so a notebook
        # cell survives the simulate branch
        self.sim_job: 'Optional[SimulatedJob]' = None
        self._exit_after_simulate = True
        self._simulate_viewer = True
        self._sim_builder = None
        self._sim_config = None
        self.viewer_bundle = None

    @property
    def active(self):
        return self._sequence is not None

    # ------------------------------------------------------------------
    # prepare(): select the sequence, register its data containers
    # ------------------------------------------------------------------

    def use(self, sequence, simulate=False, simulate_duration=200.e-6,
            simulate_shots=1, simulate_web_plot=None, simulate_viewer=True):
        """Select the per-shot OPX sequence for this run.

        Call in prepare(), before finish_prepare() (the measurement data
        containers must exist before the run is registered). ``sequence``
        is an OPXSequence object (import it from
        kexp.experiments.opx_sequences, or define one inline with
        @opx_sequence) or the registered name of one already imported.

        simulate=True: at finish_prepare the program is built and sent to
        the QOP simulator instead of executed, the waveform report is
        plotted, and the process exits before any ARTIQ hardware runs.
        Use save_data=False for simulation runs.

        simulate_shots: how many scheduled shots the simulated program
        loops over (default 1 -- just the run's first shot, i.e. every
        scanned parameter at its first scheduled scan value and everything
        else at its prepare() value). Under shuffle=True the first
        scheduled value is random; pass shuffle=False to finish_prepare for
        a deterministic single-shot simulation. 0 or None simulates the
        full scan. The provenance/execute program is never scoped -- only
        the simulation is.

        simulate_viewer=True (default): open the interactive pulse viewer
        (waxx.util.seqview) on the simulation -- a separate window with
        every simulated pulse linked to the sequence line that made it.
        Re-running a simulation updates an open viewer in place.

        simulate_web_plot: the QM waveform report (a browser plot). None
        (default) means "only when the viewer is off"; True forces it on,
        False skips it. The job is always kept on self.sim_job, so fetch
        get_simulated_samples() from it and plot however you like.
        """
        if self._sequence is not None:
            raise RuntimeError("[opx] use() called twice for one run.")
        seq = get_sequence(sequence)

        cmap = self._map_builder(self._expt)
        for role in seq.claims:
            cmap.spec(role)   # unknown role -> loud KeyError now

        data = self._expt.data
        for key, n_per_shot in seq.measurements.items():
            if key in getattr(data, 'keys', []) or hasattr(data, key):
                raise ValueError(
                    f"[opx] data container key {key!r} already exists; "
                    f"pick another name in the sequence's measurements.")
            setattr(data, key,
                    data.add_data_container((n_per_shot,), np.float64))
        if seq.measurements:
            setattr(data, VALID_MASK_KEY,
                    data.add_data_container((1,), np.int32))

        self._sequence = seq
        self._simulate = bool(simulate)
        self._simulate_duration = float(simulate_duration)
        self._simulate_shots = int(simulate_shots or 0)
        self._simulate_viewer = bool(simulate_viewer)
        self._simulate_web_plot = (not self._simulate_viewer
                                   if simulate_web_plot is None
                                   else bool(simulate_web_plot))
        console.info(f"[opx] using sequence {seq.name!r} "
                     f"(claims={seq.claims}, measurements={seq.measurements})"
                     + (" [SIMULATE]" if simulate else ""),
                     level=console.VERBOSE)
        if simulate and self._expt.run_info.save_data:
            print("[opx] WARNING: simulate=True with save_data=True -- a "
                  "run id will be claimed for a run that never happens. "
                  "Prefer save_data=False for simulation.")

    # ------------------------------------------------------------------
    # finish_prepare(): build, compile, execute
    # ------------------------------------------------------------------

    def on_finish_prepare(self):
        """Called by kexp Base.finish_prepare after the wax part: xvars are
        repeated and shuffled, so the per-shot tables are in true execution
        order."""
        if not self.active:
            return
        expt = self._expt
        seq = self._sequence

        tables = build_shot_tables(expt)
        self._n_shots = tables.n_shots
        self._map = self._map_builder(expt)
        config = self._config_builder(expt)

        builder = OPXProgramBuilder(seq, self._map, tables, self._n_shots)
        prog, ctx = builder.trace()
        self._stream_roles = dict(ctx._stream_roles)
        check_live_adjust_conflicts(expt, tables)

        # Connect before generating the provenance script: qm capabilities
        # are initialized by the QMM connection, and generate_qua_script
        # drops the config section without them ("Could not generate a
        # loaded config").
        _install_qm_log_gate()   # before the first qm import
        from qm import QuantumMachinesManager, generate_qua_script
        self._qmm = QuantumMachinesManager(host=self._host,
                                           cluster_name=self._cluster)

        # provenance: the exact program next to the run's other sources
        try:
            expt._extra_file_texts[QUA_SOURCE_ATTR] = \
                generate_qua_script(prog, config)
        except Exception as e:
            print(f"[opx] WARNING: could not serialize the QUA program for "
                  f"provenance: {e}")

        if self._simulate:
            # Re-trace for the simulator: without the per-shot
            # wait_for_trigger (it has no external trigger source, so the
            # real program would park on the first wait forever), and scoped
            # to the first simulate_shots scheduled shots -- slicing the
            # tables keeps each simulated shot's values exactly what the
            # real run's corresponding shot would use. Provenance above
            # keeps the real, full program.
            n_sim = self._simulate_shots or self._n_shots
            n_sim = min(n_sim, self._n_shots)
            tables_sim = ShotTables(
                {k: col[:n_sim].copy()
                 for k, col in tables.columns.items()}, n_sim)
            builder_sim = OPXProgramBuilder(seq, self._map, tables_sim, n_sim)
            prog_sim, _ = builder_sim.trace(skip_triggers=True)
            self._sim_builder = builder_sim
            self._sim_config = config
            console.info(f"[opx] simulating the first {n_sim} of "
                         f"{self._n_shots} scheduled shot(s) (triggers "
                         f"skipped -- shots run back-to-back on the "
                         f"simulated timeline).")
            self._run_simulation(prog_sim, config)
            if self._simulate_viewer and self.sim_job is not None:
                self.open_viewer(prog_sim)
            if self._exit_after_simulate:
                raise SystemExit(
                    "[opx] simulation complete -- exiting before any ARTIQ "
                    "hardware runs.")
            console.info("[opx] simulation complete; samples/report on "
                         "self.sim_job.")
            return

        self._qm = self._qmm.open_qm(config)
        self._job = self._qm.execute(prog)
        if not self._atexit_registered:
            # a crashed ARTIQ process must not leave a parked job holding
            # the machine (best effort; open_qm from the next run would
            # also displace it)
            atexit.register(self._halt_quietly)
            self._atexit_registered = True
        streams = ", ".join(
            f"{k} ({n}/shot)" if n > 1 else k
            for k, n in seq.measurements.items()) or "none"
        console.info(f"[opx] {seq.name!r}: job running "
                     f"({self._n_shots} shots, streams: {streams})")

    def _run_simulation(self, prog, config) -> 'SimulatedJob':
        from qm import SimulationConfig
        n_cc = max(4, int(round(self._simulate_duration * 1e9 / 4)))
        job = self._qmm.simulate(config, prog,
                                 SimulationConfig(duration=n_cc))
        self.sim_job = job
        if not self._simulate_web_plot:
            return job
        samples = job.get_simulated_samples()
        report = job.get_simulated_waveform_report()
        if report is not None:
            report.create_plot(samples, plot=True)
        return job

    # ------------------------------------------------------------------
    # pulse viewer
    # ------------------------------------------------------------------

    def build_viewer_bundle(self, prog_sim=None):
        """The seqview bundle for the last simulation (see
        kexp.control.opx.viewer). Needs a completed simulate()."""
        if self.sim_job is None or getattr(self, '_sim_builder', None) is None:
            raise RuntimeError("[opx] no simulation to view -- run with "
                               "simulate=True first.")
        from kexp.control.opx.viewer import build_bundle
        qua_sim = ''
        if prog_sim is not None:
            try:
                from qm import generate_qua_script
                qua_sim = generate_qua_script(prog_sim, self._sim_config)
            except Exception as e:
                print(f"[opx] NOTE: could not serialize the simulated program "
                      f"for the viewer: {e}")
        qua_real = self._expt._extra_file_texts.get(QUA_SOURCE_ATTR, '')
        seq = self._sequence
        n_sim = self._sim_builder.n_shots
        dur_ns = self._simulate_duration * 1e9
        title = f"{seq.name}  ·  {n_sim} of {self._n_shots} shot(s)  ·  "
        title += (f"{dur_ns / 1e3:g} µs window")
        info = {
            'title': title,
            'subtitle': f"claims {seq.claims}, measurements {seq.measurements}",
            'sequence': seq.name,
            'shots simulated': n_sim,
            'shots scheduled': self._n_shots,
            'simulated window': f"{dur_ns / 1e3:g} µs",
            'triggers': 'skipped (shots run back-to-back on the simulated timeline)',
            'simulator job': str(getattr(self.sim_job, 'id', '')),
            'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        return build_bundle(self.sim_job, self._sim_builder, self._map,
                            self._sim_config, dur_ns, qua_sim=qua_sim,
                            qua_real=qua_real, info=info, sequence=seq)

    def open_viewer(self, prog_sim=None, inline=False, reuse=True):
        """Open (or refresh) the pulse viewer on the last simulation."""
        try:
            bundle = self.build_viewer_bundle(prog_sim)
        except Exception as e:
            print(f"[opx] WARNING: pulse viewer bundle failed: {e!r}")
            import traceback
            traceback.print_exc()
            return None
        self.viewer_bundle = bundle
        from kexp.control.opx.viewer import show_bundle
        out = show_bundle(bundle, inline=inline, reuse=reuse,
                          name=self._sequence.name)
        n_err = sum(1 for w in bundle.meta['warnings'] if w['level'] == 'error')
        console.info(f"[opx] pulse viewer: {len(bundle.pulses)} pulses, "
                     f"{len(bundle.events)} events"
                     + (f", {n_err} error-level warning(s)" if n_err else '')
                     + (f" -> {out}" if isinstance(out, str) else ''))
        return out

    # ------------------------------------------------------------------
    # end(): fetch, fill containers, halt
    # ------------------------------------------------------------------

    def finish(self, timeout=30.):
        """Fetch the job's streams into the registered data containers and
        halt the job. Called by kexp Base.end() before the data is saved;
        safe to call by hand first (idempotent)."""
        if not self.active or self._finished:
            return
        self._finished = True
        if self._job is None:
            return
        try:
            fetched, counts = self._fetch_streams(timeout=timeout)
            self.fill_containers(self._expt, self._sequence, self._map,
                                 self._stream_roles, fetched, counts,
                                 self._n_shots)
        finally:
            self._halt_quietly()

    def _fetch_streams(self, timeout=30.):
        """Poll each stream until every shot's buffer arrived (or timeout:
        an aborted run simply has fewer), then fetch."""
        seq = self._sequence
        handles = self._job.result_handles
        deadline = time.monotonic() + float(timeout)
        fetched, counts = {}, {}
        for key in seq.measurements:
            h = handles.get(key)
            if h is None:
                print(f"[opx] WARNING: no result stream {key!r} on the job.")
                fetched[key], counts[key] = None, 0
                continue
            # An aborted run has fewer shots than scheduled: wait only for
            # the ones ARTIQ completed (an OPX shot ends before its ARTIQ
            # shot does), then take whatever the job streamed.
            n_done = int(getattr(self._expt, '_shot_complete_count',
                                 self._n_shots))
            n_wait = min(self._n_shots, n_done)
            n = h.count_so_far()
            while n < n_wait and time.monotonic() < deadline:
                time.sleep(0.1)
                n = h.count_so_far()
            arr = h.fetch_all() if n else None
            if arr is not None and getattr(arr.dtype, 'names', None):
                arr = arr['value']
            fetched[key] = np.asarray(arr) if arr is not None else None
            counts[key] = int(n)
        return fetched, counts

    @staticmethod
    def fill_containers(expt, seq, cmap, stream_roles, fetched, counts,
                        n_shots):
        """Write fetched per-shot arrays (execution order) into the
        DataVault containers; the normal end-of-run unshuffle handles the
        rest. Static and side-effect-free beyond the containers, so it is
        directly testable without a job."""
        if not seq.measurements:
            return
        n_valid = min([counts.get(k, 0) for k in seq.measurements])
        for key, n_per_shot in seq.measurements.items():
            dc = getattr(expt.data, key)
            target = np.full((n_shots, n_per_shot), np.nan)
            arr = fetched.get(key)
            n = min(counts.get(key, 0), n_shots)
            if arr is not None and n > 0:
                vals = np.asarray(arr, dtype=float).reshape(-1, n_per_shot)
                role = stream_roles.get(key)
                t_int = cmap.spec(role).t_integration_s if role else None
                if t_int:
                    vals = demod2volts(vals, t_int)
                else:
                    print(f"[opx] NOTE: {key!r} stored as raw integration "
                          f"units (no integration window length known).")
                target[:n] = vals[:n]
            dc._run_data = target.reshape(dc._run_data.shape)
            dc._data_gotten = True

        mask_dc = getattr(expt.data, VALID_MASK_KEY)
        mask = np.zeros(n_shots, dtype=np.int32)
        mask[:n_valid] = 1
        mask_dc._run_data = mask.reshape(mask_dc._run_data.shape)
        mask_dc._data_gotten = True

        if n_valid < n_shots:
            print(f"[opx] *** OPX data present for {n_valid} of {n_shots} "
                  f"shots; the remainder are NaN and flagged 0 in "
                  f"data.{VALID_MASK_KEY}. ***")
        else:
            console.info(f"[opx] data complete: {n_valid}/{n_shots} shots.")

    def _halt_quietly(self):
        try:
            if self._job is not None:
                self._job.halt()
        except Exception:
            pass
        try:
            if self._qm is not None:
                self._qm.close()
        except Exception:
            pass
        self._job = None
        self._qm = None
