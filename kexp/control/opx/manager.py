"""OPXManager -- the experiment-facing handle (Base assigns self.opx).

Lifecycle against the experiment:

    prepare():           self.opx.use(sequence)      # registers containers,
                                                     #   connects to the QMM
    finish_prepare():    -> on_finish_prepare()      # tables, trace, compile,
                                                     #   execute (job parks on
                                                     #   its first trigger)
    scan_kernel():       handoff_to_quantum_machines() /
                         wait_for_quantum_machines_handback()  (control.py)
    analyze() -> end():  -> finish()                 # fetch streams into the
                                                     #   containers, halt

Constructed inert and host-only: nothing imports qm until use(), so kexp
imports cleanly on machines without qm-qua installed, and ARTIQ kernel
compilation never sees it. use() connects to the QMM (an unreachable OPX
fails in prepare(), before a run id is claimed).

Data integrity on incomplete runs (abort, underflow with save opted in):
shots the OPX never ran are NaN (float containers) / -1 (int containers),
an opx_data_valid mask container (0/1, unshuffled with everything else)
records exactly which shots carry real data, and the completed/expected
counts are printed and never inferred. The OPX's own shot counter is echoed
per shot (opx_shot_index) and checked against 0, 1, 2, ...: the mask is cut
at the first mismatch.

Provenance written into the run file (extra_file_texts -> HDF5 attrs):
opx_qua_program (the exact program + config), opx_machine (the component
tree, when the channel map carries one), opx_shot_tables (per-shot values
of every parameter the program read, in SI and execution order, the
shot-array shapes, qm version, host/cluster, job id).

Generic (future waxx.control.opx): no kexp imports -- the lab wires host,
cluster, channel map and config through the factory in opx_config.py.
"""

import atexit
import json
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

from kexp.control.opx.sequence import get_sequence, Stream
from kexp.control.opx.params_bridge import (build_shot_tables, ShotTables,
                                            derived_dependents)
from kexp.control.opx.builder import (OPXProgramBuilder, SHOT_INDEX_KEY,
                                      SHOT_INDEX_STREAM, RESERVED_STREAMS)
from kexp.control.opx.units import demod2volts

VALID_MASK_KEY = 'opx_data_valid'
QUA_SOURCE_ATTR = 'opx_qua_program'
MACHINE_ATTR = 'opx_machine'
SHOT_TABLES_ATTR = 'opx_shot_tables'

# placeholder in int containers for shots without OPX data (the float
# containers hold NaN); data.opx_data_valid is the authoritative flag
INT_MISSING = -1


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
    (Config-time parameters are in tables.accessed too, so this covers
    them.)
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


def _xvar_keys(expt):
    names = getattr(expt, 'xvarnames', None)
    if names is None:
        names = [xv.key for xv in getattr(expt, 'scan_xvars', [])]
    return list(names)


def check_config_time_xvars(expt, config_time_params):
    """Refuse a run that scans a parameter compiled into the QUA config
    (acquire/integration windows, handshake windows, ...): the config is
    built ONCE per run at the first scheduled value, so a scan of one of
    these would run every shot at that value while the file says
    otherwise."""
    keys = tuple(config_time_params or ())
    if not keys:
        return
    scanned = [k for k in _xvar_keys(expt) if k in keys]
    if scanned:
        raise RuntimeError(
            f"[opx] {scanned} is scanned as an xvar but is compiled into "
            f"the OPX config once per run (config-time parameters: "
            f"{list(keys)}). The OPX would run every shot at the first "
            f"scheduled value. Take one run per value instead.")


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


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.integer, np.floating, np.bool_)):
        return o.item()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Stream):
        return {'shape': list(o.shape),
                'dtype': 'int' if o.dtype is int else 'float'}
    return str(o)


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
        self._stream_specs = {}       # {key: Stream} of every stream fetched
        self._measurements = {}       # {key: Stream} resolved at use()
        self._host_data = {}          # {key: Stream} resolved at use()
        self._host_values = {}        # {key: ndarray} from the trace
        self._shot_arrays = {}        # {key: shape} from the trace
        self._config_time_params = ()
        self._shot_tables_doc = None
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
    # QMM connection
    # ------------------------------------------------------------------

    def _call_map_builder(self, expt, tables=None):
        """map_builder(expt, tables) when the builder accepts the tables
        (the lab's kexp_channel_map does), else map_builder(expt)."""
        import inspect
        if tables is not None:
            try:
                params = inspect.signature(self._map_builder).parameters
            except (TypeError, ValueError):
                params = {}
            if len(params) >= 2 or any(
                    p.kind is inspect.Parameter.VAR_POSITIONAL
                    for p in params.values()):
                return self._map_builder(expt, tables)
        return self._map_builder(expt)

    def _connect(self):
        """Connect to the QuantumMachinesManager (once). The qm log gate is
        installed before the first import so qm's INFO chatter follows the
        run verbosity. An unreachable OPX raises here."""
        if self._qmm is not None:
            return self._qmm
        _install_qm_log_gate()   # before the first qm import
        from qm import QuantumMachinesManager
        try:
            self._qmm = QuantumMachinesManager(host=self._host,
                                               cluster_name=self._cluster)
        except Exception as e:
            raise RuntimeError(
                f"[opx] cannot reach the OPX (host {self._host!r}, cluster "
                f"{self._cluster!r}): {e!r}. Refused in prepare() so no run "
                f"id is claimed for a run that cannot happen.") from e
        return self._qmm

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
        The sequence's declared shapes are resolved here against the live
        ExptParams (callable specs such as ``lambda p: p.N_pulses``), and
        the QMM connection is made here too, so a missing OPX or a bad
        declaration fails before a run id is claimed.

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
        expt = self._expt

        cmap = self._map_builder(expt)
        for role in seq.claims:
            cmap.spec(role)   # unknown role -> loud KeyError now
        self._config_time_params = tuple(
            getattr(cmap, 'config_time_params', ()) or ())
        # early, loud: xvars declared before use() are visible now (the
        # authoritative check runs again at finish_prepare)
        check_config_time_xvars(expt, self._config_time_params)

        params = getattr(expt, 'params', None)
        measurements = seq.resolve_measurements(params)
        host_data = seq.resolve_host_data(params)

        data = expt.data
        reserved = (VALID_MASK_KEY, *RESERVED_STREAMS)
        for key, spec in {**measurements, **host_data}.items():
            if key in reserved:
                raise ValueError(
                    f"[opx] data key {key!r} is reserved by the OPX manager; "
                    f"pick another name in the sequence's declarations.")
            if key in getattr(data, 'keys', []) or hasattr(data, key):
                raise ValueError(
                    f"[opx] data container key {key!r} already exists; "
                    f"pick another name in the sequence's declarations.")
            setattr(data, key, data.add_data_container(spec.shape,
                                                       spec.np_dtype))
        for key in reserved:
            if hasattr(data, key):
                raise ValueError(
                    f"[opx] data container key {key!r} already exists.")
            setattr(data, key, data.add_data_container((1,), np.int32))

        self._sequence = seq
        self._measurements = measurements
        self._host_data = host_data
        self._simulate = bool(simulate)
        self._simulate_duration = float(simulate_duration)
        self._simulate_shots = int(simulate_shots or 0)
        self._simulate_viewer = bool(simulate_viewer)
        self._simulate_web_plot = (not self._simulate_viewer
                                   if simulate_web_plot is None
                                   else bool(simulate_web_plot))
        console.info(f"[opx] using sequence {seq.name!r} "
                     f"(claims={seq.claims}, measurements={measurements}"
                     + (f", host_data={host_data}" if host_data else '')
                     + ")" + (" [SIMULATE]" if simulate else ""),
                     level=console.VERBOSE)
        save_data = bool(getattr(getattr(expt, 'run_info', None),
                                 'save_data', False))
        if simulate and save_data:
            print("[opx] WARNING: simulate=True with save_data=True -- a "
                  "run id will be claimed for a run that never happens. "
                  "Prefer save_data=False for simulation.")

        # connect now: an unreachable OPX must fail before finish_prepare
        # claims a run id
        self._connect()

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
        # the map (and the Machine it carries, saved as provenance) is built
        # from the same per-shot tables as the config, so a scanned
        # transition frequency is recorded at the first executed shot's
        # value on both; a map builder that takes only the experiment
        # (tests, OPXBench stand-ins) is still accepted
        self._map = self._call_map_builder(expt, tables)
        cfg_keys = tuple(getattr(self._map, 'config_time_params', ())
                         or self._config_time_params)
        self._config_time_params = cfg_keys
        check_config_time_xvars(expt, cfg_keys)
        # the config reads these once per run: record them as dependencies
        # of the program so the Adjust-panel check covers them too
        for key in cfg_keys:
            if tables.has(key):
                tables.accessed.add(key)
        config = self._config_builder(expt, tables)

        # the containers were registered at use() with shapes resolved on
        # the live params; a shape that moved since (a parameter changed
        # after use()) would silently mis-size the data
        params = getattr(expt, 'params', None)
        measurements = seq.resolve_measurements(params)
        host_data = seq.resolve_host_data(params)
        if measurements != self._measurements or host_data != self._host_data:
            raise RuntimeError(
                f"[opx] the sequence's data shapes changed between use() "
                f"({self._measurements}, {self._host_data}) and "
                f"finish_prepare ({measurements}, {host_data}): a parameter "
                f"a shape depends on was modified after use(). Set such "
                f"parameters before self.opx.use(...).")

        builder = OPXProgramBuilder(seq, self._map, tables, self._n_shots,
                                    params=params)
        prog, ctx = builder.trace()
        self._stream_roles = dict(ctx._stream_roles)
        self._stream_specs = builder.stream_specs()
        self._host_values = dict(ctx._host_data_values)
        self._shot_arrays = {k: tuple(int(n) for n in v.shape)
                             for k, v in ctx._shot_arrays.items()}
        check_live_adjust_conflicts(expt, tables)

        # Connect (normally done in use()) before generating the provenance
        # script: qm capabilities are initialized by the QMM connection,
        # and generate_qua_script drops the config section without them
        # ("Could not generate a loaded config").
        self._connect()
        self._write_provenance(prog, config, tables, ctx)

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
            builder_sim = OPXProgramBuilder(seq, self._map, tables_sim, n_sim,
                                            params=params)
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
        job_id = getattr(self._job, 'id', None)
        if job_id is not None and self._shot_tables_doc is not None:
            self._shot_tables_doc['job_id'] = str(job_id)
            self._write_text(SHOT_TABLES_ATTR, self._shot_tables_doc)
        streams = ", ".join(
            f"{k} {list(s.shape)}/shot" if s.n > 1 else k
            for k, s in self._measurements.items()) or "none"
        console.info(f"[opx] {seq.name!r}: job running "
                     f"({self._n_shots} shots, streams: {streams})")

    # ------------------------------------------------------------------
    # provenance
    # ------------------------------------------------------------------

    def _texts(self):
        expt = self._expt
        if not hasattr(expt, '_extra_file_texts'):
            expt._extra_file_texts = {}
        return expt._extra_file_texts

    def _write_text(self, attr, doc):
        try:
            self._texts()[attr] = json.dumps(doc, default=_json_default)
        except Exception as e:
            print(f"[opx] WARNING: could not serialize {attr!r} for "
                  f"provenance: {e!r}")

    def _write_provenance(self, prog, config, tables, ctx):
        """The exact program next to the run's other sources, the machine
        description when the map carries one, and the per-shot tables of
        every parameter the program depends on."""
        from qm import generate_qua_script
        texts = self._texts()
        try:
            texts[QUA_SOURCE_ATTR] = generate_qua_script(prog, config)
        except Exception as e:
            print(f"[opx] WARNING: could not serialize the QUA program for "
                  f"provenance: {e}")

        machine = getattr(self._map, 'machine', None)
        if machine is not None and hasattr(machine, 'to_dict'):
            try:
                self._write_text(MACHINE_ATTR, machine.to_dict())
            except Exception as e:
                print(f"[opx] WARNING: could not serialize the OPX machine "
                      f"for provenance: {e!r}")

        try:
            import qm
            qm_version = str(getattr(qm, '__version__', ''))
        except Exception:
            qm_version = ''
        accessed = sorted(k for k in tables.accessed if tables.has(k))
        doc = {
            'sequence': self._sequence.name,
            'n_shots': int(tables.n_shots),
            'xvardims': [int(d) for d in getattr(self._expt, 'xvardims', [])],
            'xvarnames': _xvar_keys(self._expt),
            'accessed': accessed,
            'config_time_params': list(self._config_time_params),
            'columns': {k: tables.column(k).tolist() for k in accessed},
            'shot_arrays': {k: list(v) for k, v in self._shot_arrays.items()},
            'measurements': {k: _json_default(v)
                             for k, v in self._measurements.items()},
            'host_data': {k: _json_default(v)
                          for k, v in self._host_data.items()},
            'qm_version': qm_version,
            'host': self._host,
            'cluster': self._cluster,
            'simulate': bool(self._simulate),
        }
        self._shot_tables_doc = doc
        self._write_text(SHOT_TABLES_ATTR, doc)

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
        qua_real = self._texts().get(QUA_SOURCE_ATTR, '')
        seq = self._sequence
        n_sim = self._sim_builder.n_shots
        dur_ns = self._simulate_duration * 1e9
        title = f"{seq.name}  ·  {n_sim} of {self._n_shots} shot(s)  ·  "
        title += (f"{dur_ns / 1e3:g} µs window")
        info = {
            'title': title,
            'subtitle': f"claims {seq.claims}, measurements {self._measurements}",
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
        """Fetch the job's streams into the registered data containers,
        run the sequence's finish hook, and halt the job. Called by kexp
        Base.end() before the data is saved; safe to call by hand first.

        Re-entrant on failure: if the fetch or the fill raises, nothing is
        marked finished and the job is left running, so a second call (a
        transient timeout, a fixed hook) retries from scratch. After a
        successful fill the job is halted and the manager is finished; a
        finish-hook error is then raised to the caller with the raw
        containers already filled (derived containers can be recomputed
        offline from them).
        """
        if not self.active or self._finished:
            return
        if self._job is None:
            return
        fetched, counts = self._fetch_streams(timeout=timeout)
        self.fill_containers(self._expt, self._sequence, self._map,
                             self._stream_roles, fetched, counts,
                             self._n_shots, specs=self._stream_specs,
                             host_data=self._host_values)
        self._finished = True
        try:
            hook = getattr(self._sequence, 'finish', None)
            if hook is not None:
                hook(self._expt, self._expt.data)
        finally:
            self._halt_quietly()

    def _fetch_streams(self, timeout=30.):
        """Poll each stream until every shot's buffer arrived (or timeout:
        an aborted run simply has fewer), then fetch. Timestamp and echo
        streams are ordinary streams here."""
        specs = self._stream_specs or {
            **self._measurements, **RESERVED_STREAMS}
        handles = self._job.result_handles
        deadline = time.monotonic() + float(timeout)
        fetched, counts = {}, {}
        for key in specs:
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
                        n_shots, specs=None, host_data=None):
        """Write fetched per-shot arrays (execution order) into the
        DataVault containers; the normal end-of-run unshuffle handles the
        rest. Static and side-effect-free beyond the containers, so it is
        directly testable without a job.

        specs: {key: Stream} of the fetched streams (default: the
        sequence's static measurements). Float streams -> float64
        containers, NaN where missing; volts conversion only for keys a
        ctx.measure produced (stream_roles). Int streams -> int64 (or the
        container's own int dtype), INT_MISSING where missing, never
        converted. host_data: {key: (n_shots, *shape)} host values written
        as-is. The shot-index echo (SHOT_INDEX_KEY), when fetched, must
        read 0, 1, 2, ...: the valid mask is cut at the first mismatch.
        """
        if specs is None:
            specs = seq.resolve_measurements(None)
        specs = dict(specs)
        data = expt.data
        if not specs and not host_data and not hasattr(data, VALID_MASK_KEY):
            return
        n_valid = (min(min(int(counts.get(k, 0)), n_shots) for k in specs)
                   if specs else 0)

        # shot-counter echo: the stream must hold 0, 1, 2, ... in order
        echo = fetched.get(SHOT_INDEX_KEY) if fetched else None
        if echo is not None and SHOT_INDEX_KEY in specs:
            got = np.asarray(echo).reshape(-1)
            got = got[:min(int(counts.get(SHOT_INDEX_KEY, 0)), n_shots)]
            expect = np.arange(got.size)
            bad = np.flatnonzero(got != expect)
            if bad.size:
                first = int(bad[0])
                print(f"[opx] *** OPX shot counter echo disagrees with the "
                      f"shot order from shot {first}: the OPX reported shot "
                      f"{int(got[first])} where {first} was expected "
                      f"({bad.size} mismatching of {got.size}). OPX data "
                      f"from shot {first} on is flagged 0 in "
                      f"data.{VALID_MASK_KEY} (values kept as fetched). ***")
                n_valid = min(n_valid, first)

        for key, spec in specs.items():
            dc = getattr(data, key, None)
            if dc is None:
                if key in RESERVED_STREAMS:
                    continue      # a stand-in without the reserved containers
                raise KeyError(f"[opx] no data container {key!r} registered "
                               f"for the fetched stream.")
            is_int = spec.dtype is int
            fill = INT_MISSING if is_int else np.nan
            target = np.full((n_shots, *spec.shape), fill,
                             dtype=np.int64 if is_int else np.float64)
            arr = fetched.get(key) if fetched else None
            n = min(int(counts.get(key, 0)), n_shots)
            if arr is not None and n > 0:
                if is_int:
                    vals = np.rint(np.asarray(arr, dtype=float)).astype(
                        np.int64).reshape(-1, *spec.shape)
                else:
                    vals = np.asarray(arr, dtype=float).reshape(-1, *spec.shape)
                    role = stream_roles.get(key)
                    t_int = cmap.spec(role).t_integration_s if role else None
                    if t_int:
                        vals = demod2volts(vals, t_int)
                    else:
                        print(f"[opx] NOTE: {key!r} stored as raw integration "
                              f"units (no integration window length known).")
                n = min(n, vals.shape[0])
                target[:n] = vals[:n]
            dc._run_data = target.reshape(dc._run_data.shape).astype(
                dc._run_data.dtype, copy=False)
            dc._data_gotten = True

        for key, vals in (host_data or {}).items():
            dc = getattr(data, key, None)
            if dc is None:
                raise KeyError(f"[opx] no data container {key!r} registered "
                               f"for the host data.")
            vals = np.asarray(vals)
            if vals.size != dc._run_data.size:
                raise ValueError(
                    f"[opx] host data {key!r} has {vals.size} values, the "
                    f"container holds {dc._run_data.size}.")
            dc._run_data = vals.reshape(dc._run_data.shape).astype(
                dc._run_data.dtype, copy=False)
            dc._data_gotten = True

        mask_dc = getattr(data, VALID_MASK_KEY, None)
        if mask_dc is not None:
            mask = np.zeros(n_shots, dtype=np.int32)
            mask[:n_valid] = 1
            mask_dc._run_data = mask.reshape(mask_dc._run_data.shape)
            mask_dc._data_gotten = True

        if n_valid < n_shots:
            print(f"[opx] *** OPX data present for {n_valid} of {n_shots} "
                  f"shots; the remainder are NaN (int containers: "
                  f"{INT_MISSING}) and flagged 0 in data.{VALID_MASK_KEY}. ***")
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
