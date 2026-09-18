"""Time every phase between `ar <file>` and the first shot.

A drop-in replacement for artiq_run that prints where the time goes:

    import -> build -> prepare -> compile (stitch / typecheck / IR / LLVM /
    link / strip) -> upload -> kernel start -> first RPC -> ... -> analyze

Nothing in ARTIQ, waxx or kexp is edited. The hooks wrap functions at runtime,
in this process only; a normal `ar` run is unaffected. The experiment runs for
real (same hardware activity as `ar`), so the usual run rules apply.

Usage -- the `art` launcher (k-exp/kexp/_bat/shortcuts/art.bat, on PATH) is
`ar` with the timer:

    art <file>.py
    art <file>.py --timing-json C:\\some\\dir\\timing.jsonl    append one JSON record per run
    art --check-hooks                                         verify hook targets, run nothing

Long form. Run BY PATH, not with -m (importing the kexp package here would hide
its import cost from the measurement). Note %kpy% is the venv *activate* script,
not an interpreter, so it needs `& python`:

    %kpy% & python k-exp\\kexp\\util\\profiling\\startup_timer.py --device-db %db% <file>.py

Everything except --timing-json / --check-hooks is passed to artiq_run as is.
"""

import atexit
import functools
import json
import os
import sys
import time

_T0 = time.perf_counter()
_MIN_REPORT_S = 0.001


class _Timeline:
    def __init__(self):
        self.spans = []        # (name, start_s, duration_s, depth)
        self.marks = {}        # name -> t_s
        self.counts = {}
        self._depth = 0
        self.n_compiles = 0
        self.n_rpcs = 0
        self.rpc_times = []    # completion time of every RPC served
        self.census = []       # per compile: {module: [n_functions, n_source_lines]}

    def now(self):
        return time.perf_counter() - _T0

    def mark(self, name):
        self.marks.setdefault(name, self.now())

    def wrap(self, owner, attr, name=None, after=None, first_only_mark=None,
             label_fn=None, min_s=0.0):
        """Replace owner.attr with a timed wrapper. Returns False if absent.

        label_fn(args, kwargs) -> str builds a per-call label; spans shorter
        than min_s are dropped (keeps no-op calls out of the timeline).
        """
        orig = getattr(owner, attr, None)
        if orig is None:
            return False
        label = name or attr
        tl = self

        @functools.wraps(orig)
        def timed(*args, **kwargs):
            if first_only_mark is not None:
                tl.mark(first_only_mark)
            start = tl.now()
            tl._depth += 1
            depth = tl._depth
            try:
                result = orig(*args, **kwargs)
            finally:
                tl._depth -= 1
                dur = tl.now() - start
                if dur >= min_s:
                    this_label = label
                    if label_fn is not None:
                        try:
                            this_label = label_fn(args, kwargs)
                        except Exception:
                            pass
                    tl.spans.append((this_label, start, dur, depth))
            if after is not None:
                try:
                    after(args, kwargs, result)
                except Exception as exc:     # never let a probe break a run
                    tl.counts.setdefault("probe_errors", []).append(repr(exc))
            return result

        setattr(owner, attr, timed)
        return True


TL = _Timeline()


def _dds_init_lines(experiment):
    """Devices.init_all_dds prints nothing; it leaves its outcome on the experiment."""
    report = getattr(experiment, "_dds_init_report", None)
    if report is None:
        return []
    lines = ["", f"  DDS INIT: full init on {report['n_full']} of {report['n_channels']} channels, "
                 f"{report['t_total_s'] * 1e3:.1f} ms on the core device "
                 f"(check pass {report['t_check_pass_s'] * 1e3:.1f} ms)"]
    for f in getattr(experiment, "_dds_init_failures", []):
        lines.append(f"    urukul {f['urukul']} ch {f['ch']}: {f['reason']} (raw {f['raw']})")
    return lines


def _function_census(functions):
    """What got compiled: {module: [n_functions, n_source_lines]} over every
    function the stitcher embedded (kernels, portables, RPC stubs)."""
    import inspect
    census = {}
    for fn in functions:
        # Methods are keyed as SpecializedFunction(instance_type, host_function);
        # the source lives at host_function.artiq_embedded.function, which is a
        # str for kernel_from_string bodies.
        host = getattr(fn, "host_function", fn)
        info = getattr(host, "artiq_embedded", None)
        raw = info.function if info is not None and info.function is not None else host
        if isinstance(raw, str):
            module, n_lines = "<generated: kernel_from_string>", raw.count("\n") + 1
        else:
            module = getattr(raw, "__module__", None) or "?"
            try:
                n_lines = len(inspect.getsourcelines(raw)[0])
            except Exception:
                module, n_lines = module + " (no source)", 1
        entry = census.setdefault(module, [0, 0])
        entry[0] += 1
        entry[1] += n_lines
    return census


def _rpc_bursts(times, max_gap_s=0.005, min_rpcs=50):
    """Runs of back-to-back RPCs (the per-shot param push is one ~300-RPC burst).
    Returns a list of (n_rpcs, duration_s)."""
    bursts, start, prev, n = [], None, None, 0
    for t in times:
        if prev is not None and t - prev <= max_gap_s:
            n += 1
        else:
            if n >= min_rpcs:
                bursts.append((n, prev - start))
            start, n = t, 1
        prev = t
    if n >= min_rpcs:
        bursts.append((n, prev - start))
    return bursts


# Host-side steps inside prepare() / analyze(), as (module, class, method, label).
# Only HOST-ONLY methods belong here: a method that a kernel calls (an RPC target
# such as tweezer.awg_init) is inspected by the ARTIQ embedder and is left alone.
_HOST_STEPS = [
    ("kexp.base.base", "Base", "__init__", "Base.__init__"),
    ("kexp.base.devices", "Devices", "prepare_devices", "prepare_devices"),
    ("kexp.config.wavemeter_id", "fzw_frame", "__init__", "wavemeter frame (TCP connect)"),
    ("kexp.base.clients", "Clients", "__init__", "Clients.__init__ (server discovery)"),
    ("kexp.control.misc.pdxc_apd_stage", "APDStageClient", "set_apd_stage", "set_apd_stage"),
    ("kexp.base.base", "Base", "finish_prepare", "finish_prepare"),
    ("waxx.base.monitor", "Monitor", "init_monitor", "monitor.init_monitor"),
    ("waxx.base.scanner", "Scanner", "init_xvars", "init_xvars"),
    ("waxx.base.scanner", "Scanner", "generate_assignment_kernels",
     "generate_assignment_kernels"),
    ("kexp.util.live_od.live_od_client", "LiveODClient", "init_run", "liveOD INIT_RUN"),
    ("kexp.util.live_od.live_od_client", "LiveODClient", "wait_cam_ready",
     "liveOD WAIT_CAM_READY"),
    ("kexp.util.live_od.live_od_client", "LiveODClient", "end_run", "liveOD END_RUN"),
    ("waxx.base.expt", "Expt", "end_wax", "end_wax"),
    ("waxx.base.monitor", "Monitor", "update_device_states", "monitor.update_device_states"),
]


def _install_host_hooks(*_):
    """Called once the experiment file is imported. Wraps only what is loaded."""
    for modname, clsname, meth, label in _HOST_STEPS:
        mod = sys.modules.get(modname)
        cls = getattr(mod, clsname, None) if mod is not None else None
        if cls is not None and meth in vars(cls):
            TL.wrap(cls, meth, label, min_s=0.001)

    client_mod = sys.modules.get("beacon.discovery.client")
    if client_mod is not None:
        def discovery_label(args, kwargs):
            server_id = args[1] if len(args) > 1 else kwargs.get("server_id", "?")
            return f"discover '{server_id}'"
        TL.wrap(client_mod.NetClient, "__init__", "discover", label_fn=discovery_label)


def _install_hooks():
    """Wrap the startup path. Returns ({hook name: installed?}, artiq_run)."""
    from artiq.frontend import artiq_run
    from artiq.master.worker_db import DeviceManager
    from artiq.coredevice.core import Core
    from artiq.coredevice.comm_kernel import CommKernel
    from artiq.compiler.embedding import Stitcher
    from artiq.compiler.module import Module
    from artiq.compiler import targets

    TL.marks["artiq_run imported"] = TL.now()
    ok = {}

    # --- host side -------------------------------------------------------
    ok["file_import"] = TL.wrap(artiq_run, "file_import",
                                "import experiment file (+kexp, waxx, ...)",
                                after=_install_host_hooks)
    def keep_experiment(args, kwargs, result):
        TL.experiment = result      # some results are left on it, e.g. _dds_init_report

    ok["_build_experiment"] = TL.wrap(artiq_run, "_build_experiment",
                                      "import + build()", after=keep_experiment)

    # --- compile ---------------------------------------------------------
    def after_compile(args, kwargs, result):
        TL.n_compiles += 1
        try:
            TL.counts.setdefault("elf_bytes", []).append(len(result[1]))
        except Exception:
            pass

    def after_finalize(args, kwargs, result):
        stitcher = args[0]
        TL.counts.setdefault("embedded_functions", []).append(len(stitcher.functions))
        TL.counts.setdefault("typed_attributes", []).append(
            stitcher.embedding_map.attribute_count())
        TL.census.append(_function_census(stitcher.functions))

    ok["Core.compile"] = TL.wrap(Core, "compile", "Core.compile (total)",
                                 after=after_compile,
                                 first_only_mark="prepare() done / compile start")
    ok["Stitcher.stitch_call"] = TL.wrap(Stitcher, "stitch_call", "stitch_call (parse entry)")
    ok["Stitcher.finalize"] = TL.wrap(Stitcher, "finalize",
                                      "stitcher.finalize (embed + type inference fixpoint)",
                                      after=after_finalize)
    ok["Module.__init__"] = TL.wrap(Module, "__init__", "Module (validators + IR)")
    ok["Target.compile"] = TL.wrap(targets.Target, "compile",
                                   "target.compile (LLVM IR gen + parse + optimize + emit)")
    ok["Target.optimize"] = TL.wrap(targets.Target, "optimize", "LLVM optimize")
    ok["Target.link"] = TL.wrap(targets.Target, "link", "link (ld.lld subprocess)")
    ok["Target.strip"] = TL.wrap(targets.Target, "strip", "strip (llvm-strip subprocess)")

    # --- core device -----------------------------------------------------
    def count_rpc(args, kwargs, result):
        TL.n_rpcs += 1
        TL.rpc_times.append(TL.now())

    # open() is called before every operation and is a no-op once connected
    ok["CommKernel.open"] = TL.wrap(CommKernel, "open", "connect to core device",
                                    min_s=0.001)
    ok["CommKernel.load"] = TL.wrap(CommKernel, "load", "upload kernel")
    ok["CommKernel.run"] = TL.wrap(CommKernel, "run", "start kernel",
                                   first_only_mark="kernel started")
    ok["CommKernel._serve_rpc"] = TL.wrap(CommKernel, "_serve_rpc", "rpc",
                                          after=count_rpc,
                                          first_only_mark="first RPC from kernel")
    ok["CommKernel.serve"] = TL.wrap(CommKernel, "serve", "kernel running (serve RPCs until exit)")

    # --- end of run ------------------------------------------------------
    ok["notify_run_end"] = TL.wrap(DeviceManager, "notify_run_end", "notify_run_end",
                                   first_only_mark="run() returned / analyze start")
    ok["close_devices"] = TL.wrap(DeviceManager, "close_devices", "close_devices",
                                  first_only_mark="analyze() done")
    return ok, artiq_run


def _report(json_path, argv):
    total = TL.now()
    spans = [s for s in TL.spans if s[0] != "rpc"]
    rpc_spans = [s for s in TL.spans if s[0] == "rpc"]
    out = sys.stderr

    print("\n" + "=" * 78, file=out)
    print("STARTUP TIMELINE   (t = seconds since this process started)", file=out)
    print("=" * 78, file=out)
    # Entries under 1 ms are left out of the printed report (the JSON keeps them).
    events = [(t, 0.0, 0, "* " + name, True) for name, t in TL.marks.items()]
    events += [(start, dur, depth, name, False) for name, start, dur, depth in spans
               if dur >= _MIN_REPORT_S]
    for start, dur, depth, name, is_mark in sorted(events, key=lambda e: (e[0], e[2])):
        if is_mark:
            print(f"  t={start:8.3f}               {name}", file=out)
        else:
            print(f"  t={start:8.3f}  {dur:9.3f} s  {'  ' * (depth - 1)}{name}", file=out)

    m = TL.marks
    summary = {}

    def span_total(label):
        return sum(d for n, _, d, _ in spans if n == label)

    summary["python + artiq_run imports"] = m.get("artiq_run imported")
    summary["experiment imports (kexp etc.)"] = span_total("import experiment file (+kexp, waxx, ...)")
    summary["build()"] = (span_total("import + build()")
                          - summary["experiment imports (kexp etc.)"])
    if "prepare() done / compile start" in m:
        build_end = max((s + d for n, s, d, _ in spans if n == "import + build()"), default=None)
        if build_end is not None:
            summary["prepare()"] = m["prepare() done / compile start"] - build_end
    summary["compile (all kernels)"] = span_total("Core.compile (total)")
    summary["upload kernel"] = span_total("upload kernel")
    if "kernel started" in m and "first RPC from kernel" in m:
        summary["kernel start -> first RPC"] = m["first RPC from kernel"] - m["kernel started"]
    summary["kernel running"] = span_total("kernel running (serve RPCs until exit)")
    if "run() returned / analyze start" in m and "analyze() done" in m:
        summary["analyze() (end_wax etc.)"] = m["analyze() done"] - m["run() returned / analyze start"]
    summary["total process"] = total

    print("\nSUMMARY", file=out)
    for key, val in summary.items():
        if val is not None and val >= _MIN_REPORT_S:
            print(f"  {key:<36s} {val:9.3f} s", file=out)
    if "kernel started" in m:
        print(f"  {'>> submission -> kernel running':<36s} {m['kernel started']:9.3f} s", file=out)
    print(f"\n  kernels compiled: {TL.n_compiles}    "
          f"RPCs served: {TL.n_rpcs} "
          f"({sum(d for _, _, d, _ in rpc_spans):.3f} s host time inside RPC handlers)", file=out)
    for key, val in TL.counts.items():
        print(f"  {key}: {val}", file=out)

    for line in _dds_init_lines(getattr(TL, "experiment", None)):
        print(line, file=out)

    bursts = _rpc_bursts(TL.rpc_times)
    if bursts:
        durs = sorted(d for _, d in bursts)
        sizes = sorted(n for n, _ in bursts)
        print(f"\n  RPC bursts (>=50 back-to-back RPCs, e.g. the per-shot param push): "
              f"{len(bursts)}", file=out)
        print(f"    median {sizes[len(sizes) // 2]} RPCs in {durs[len(durs) // 2] * 1e3:.0f} ms"
              f"   (min {durs[0] * 1e3:.0f} ms, max {durs[-1] * 1e3:.0f} ms,"
              f" total {sum(durs):.2f} s)", file=out)

    for census in TL.census:
        rows = sorted(census.items(), key=lambda kv: -kv[1][1])
        print("\n  COMPILED FUNCTIONS BY MODULE          functions   source lines", file=out)
        for module, (n_fn, n_lines) in rows[:14]:
            print(f"    {module[-38:]:<38s} {n_fn:6d} {n_lines:12d}", file=out)
        rest = rows[14:]
        if rest:
            print(f"    {'(' + str(len(rest)) + ' more modules)':<38s} "
                  f"{sum(v[0] for _, v in rest):6d} {sum(v[1] for _, v in rest):12d}", file=out)
    print("=" * 78, file=out)

    if json_path:
        record = {
            "when": time.strftime("%Y-%m-%d %H:%M:%S"),
            "argv": argv,
            "summary": summary,
            "marks": TL.marks,
            "spans": [dict(name=n, start=s, duration=d, depth=k) for n, s, d, k in spans],
            "n_compiles": TL.n_compiles,
            "n_rpcs": TL.n_rpcs,
            "rpc_host_time_s": sum(d for _, _, d, _ in rpc_spans),
            "counts": TL.counts,
            "rpc_bursts": bursts,
            "dds_init": getattr(getattr(TL, "experiment", None), "_dds_init_report", None),
            "dds_init_failures": getattr(getattr(TL, "experiment", None),
                                         "_dds_init_failures", []),
            "census": TL.census,
        }
        with open(json_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        print(f"  appended record to {json_path}", file=out)


def main():
    argv = sys.argv[1:]
    json_path = None
    check_only = False
    passthrough = []
    i = 0
    while i < len(argv):
        if argv[i] == "--timing-json":
            json_path = os.path.abspath(argv[i + 1])
            i += 2
        elif argv[i] == "--check-hooks":
            check_only = True
            i += 1
        else:
            passthrough.append(argv[i])
            i += 1

    ok, artiq_run = _install_hooks()
    missing = [name for name, installed in ok.items() if not installed]
    if check_only:
        for name, installed in ok.items():
            print(f"  {'ok     ' if installed else 'MISSING'}  {name}")
        return 1 if missing else 0
    if missing:
        print(f"[startup_timer] WARNING: hook targets not found (ARTIQ changed?): {missing}",
              file=sys.stderr)

    # The report must print even when the run raises or artiq_run calls sys.exit.
    atexit.register(_report, json_path, passthrough)
    sys.argv = ["artiq_run"] + passthrough
    return artiq_run.main()


if __name__ == "__main__":
    sys.exit(main())
