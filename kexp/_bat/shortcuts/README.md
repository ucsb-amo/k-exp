# Shortcuts

`ar.lnk` runs `artiq_run --device-db %db%` directly. `kq.bat` is the run queue's command
line (`kq --help`); `ar_queue.bat` is `kq run`: it submits to the monitor server's queue and
prints the run's output as `artiq_run` would. To make `ar` submit to the queue, once the
monitor server runs the queue, replace `ar.lnk` with a copy of `ar_queue.bat` named `ar.bat`;
`artiq_run --device-db %db% <file>.py` stays the direct path, outside the queue.

`kq` also exists as `kq.exe` in `.venv\Scripts` once `uv sync` has installed waxx's console
script. Both do the same thing. Whichever folder comes first on PATH wins; within one folder
`.EXE` comes before `.BAT`.

## What changes for `%kpy% & ar ...` callers when `ar` is flipped

More than 20 places shell out to `ar`: ExptBuilder notebooks, the M-LOOP interfaces, Rydberg
and tweezer-balance builders, notebooks, and the agents' `run_lock.py`. After the flip each
call is `kq run` and goes through the queue:

- **Owner and priority.** The job is a person's, at priority 10, unless the caller's
  environment has `WAXX_OWNER=agent` (then owner agent, priority 0). `--priority N` overrides.
- **Paths are checked on kong.** The file must exist on kong and lie under the server's roots
  as seen on kong: `%code%` and `C:\lab\skynet_log` by default (`WAXX_RUN_QUEUE_ROOTS`
  overrides). A builder that writes its file to `%TEMP%` is refused with exit 6. A builder on
  another PC passes a path on its own disk, which is also refused with exit 6, unless the same
  path exists on kong. A relative path is made absolute on the caller's PC first.
- **Refused arguments.** An argument or path holding any of `& | < > ^ % " !` is refused
  (`x=50%` too, which `artiq_run` accepts), and so is one ending in a backslash.
- **One job at a time, behind the gate.** The call returns only when the job has waited its
  turn and ended. It waits behind other jobs, liveOD's run in progress, a state reset, the
  monitor starting, and, for agent jobs, a person's hold or pause. A running TOF loop is
  stopped after its run and started again when the queue is empty.
- **Output.** The job's output is streamed to stdout as before, so `Run ID: N` lines still
  parse. kq adds `[kq] ...` lines and the log's two header lines (`-- run queue ...` and
  `$ <command>`). kq's own errors go to stderr.
- **Exit codes.** 0 saved; the experiment's own code N; 1 failed with no code of its own
  (including exit 0 while liveOD did not save); 3 cancelled or skipped; 4 no queue
  beaconing; 6 refused or no answer; 130 Ctrl-C. A job is skipped when its file changed
  between submit and launch. Two builders that share one file (`kexp/experiments/ml_expt.py`)
  and overlap will skip each other's jobs.
- **The run belongs to the queue.** Killing the caller (a `subprocess` kill, a notebook
  interrupt, a closed terminal) no longer ends the run. Without a terminal, Ctrl-C leaves the
  run going. To stop it, use `kq cancel <id>`, which sends liveOD's Abort.
- **Working folder.** The job runs in the file's folder on kong (or `--cwd`), not in the
  caller's working folder.
- **Launcher tag.** The experiment sees `WAXX_LAUNCHER=kq` and `WAXX_QUEUE_JOB=<id>` and
  leaves restarting the monitor to the server.
- **run_lock.py.** The agents' `run_lock.py run -- %kpy% & ar <file>` would become a queue
  client: it would hold its lock while the job waits, the run would carry the queue's
  launcher tag instead of `run_lock`, and its Ctrl-C would end only kq. A replacement is
  staged (not installed) in `C:\lab\skynet_log\outputs\wt\kq\skill_scripts\run_lock.py`,
  with the installed version it is based on in `orig\`. It rewrites a command word `ar` to
  `artiq_run --device-db "%db%"`. It is copied over
  `.claude/skills/run-experiment/scripts/run_lock.py` at the flip, not before.

Callers that must keep running directly, outside the queue, call
`artiq_run --device-db %db% <file>.py`.
