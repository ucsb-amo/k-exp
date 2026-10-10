# Shortcuts

`ar.lnk` runs `artiq_run --device-db %db%` directly (target
`%code%\.venv\Scripts\artiq_run.exe --device-db %db%`). `artiq_run --device-db %db% <file>.py`
is and stays the direct path, outside the queue.

The run queue's command line is `kq` (`kq --help`). After `uv sync` has installed waxx's
console script it is `%code%\.venv\Scripts\kq.exe`. `kq run <file>.py` submits to the
monitor server's queue and prints the run's output as `artiq_run` would.

**Flipping `ar` to the queue**, once the monitor server runs it: point `ar.lnk` (or a new
`.lnk` named `ar`) at `%code%\.venv\Scripts\kq.exe run`. Do not use an `ar.bat`. After a
Ctrl-C, cmd asks "Terminate batch job (Y/N)?" and loses kq's exit code, which callers
read.

`kq.bat` and `ar_queue.bat` (= `kq run`) are conveniences for a terminal, with that same
caveat: after a Ctrl-C, cmd's batch prompt can swallow the exit code. When `kq.exe` and
`kq.bat` are both on PATH, the folder that comes first on PATH wins; within one folder
`.EXE` comes before `.BAT`. Both do the same thing.

## The file that runs is kong's

The queue runs the file at that path on kong, so it must match yours. kq sends a hash of
your copy, and the queue refuses the job if kong's copy differs ("your copy differs from
kong's"). From another PC, a file kq cannot read is refused too.

## What changes for `%kpy% & ar ...` callers when `ar` is flipped

More than 20 places shell out to `ar`: ExptBuilder notebooks, the M-LOOP interfaces, Rydberg
and tweezer-balance builders, notebooks, and the agents' `run_lock.py`. After the flip, each
call is `kq run` and goes through the queue:

- **Owner and place in the queue.** The job is a person's unless the caller's environment
  has `WAXX_OWNER=agent`. A person's job is placed ahead of every queued agent job; an
  agent's job goes to the end. The queue then runs in that order (`kq list` shows it), and
  `kq move` changes it. `--priority` is only a placement hint within the owner's block.
- **Paths are checked on kong.** The file must exist on kong and lie under the server's roots
  as seen on kong: `%code%` and `C:\lab\skynet_log` by default (`WAXX_RUN_QUEUE_ROOTS`
  overrides). A builder that writes its file to `%TEMP%` is refused with exit 6. A builder on
  another PC passes a path on its own disk. It is refused with exit 6 unless the same path
  exists on kong, holds the same bytes, and the builder's copy can be read. A relative path
  is made absolute on the caller's PC first.
- **Refused arguments.** An argument or path holding any of `& | < > ^ % " !` is refused
  (`x=50%` too, which `artiq_run` accepts), and so is one ending in a backslash.
- **One job at a time, behind the gate.** The call returns only when the job has waited its
  turn and ended. It waits behind other jobs, liveOD's run in progress, a state reset, the
  monitor starting, and, for agent jobs, a person's hold or pause.
- **Run loops.** A person's job stops a running TOF loop after its run in progress and starts
  it again when the queue is empty. An agent's job stops only a loop the queue or an agent
  started; it waits behind a loop a person started.
- **Output.** The job's stdout and stderr are merged into one stream: its log, which kq
  copies to stdout. `Run ID: N` lines still parse. kq adds `[kq] ...` lines and the log's two
  header lines (`-- run queue ...` and `$ <command>`). kq's own errors go to stderr.
- **No input.** The job's stdin is empty (DEVNULL). An experiment that calls `input()`
  cannot run through the queue; run it directly.
- **Exit codes.** 0 saved; the experiment's own code N; 1 failed with no code of its own
  (including exit 0 while liveOD did not save); 2 bad kq command line; 3 cancelled or
  skipped; 4 no queue beaconing; 6 refused or no answer; 130 Ctrl-C.
- **The shared builder file (`kexp/experiments/ml_expt.py`).** The queue hashes the file at
  submit and again at launch. A job is skipped (exit 3) if the file changed between the two.
  When two builders share one file and overlap, only the earlier job is skipped, and only if
  the other builder's write lands before that job's launch hash.
  - A write in the second or two between the launch hash and `artiq_run` reading the file
    runs the other builder's content under the first job's id, and nothing flags it.
  - Files the experiment imports from beside it are not hashed at all.
  - Give each builder a private file under `%code%` (or `C:\lab\skynet_log`) and never
    rewrite it while its job is queued or running.
- **The run belongs to the queue.** Killing the caller (a `subprocess` kill, a notebook
  interrupt, a closed terminal) no longer ends the run. Without a terminal, Ctrl-C leaves the
  run going. To stop it, use `kq cancel <id>`, which sends liveOD's Abort.
- **Working folder.** The job runs in the file's folder on kong (or `--cwd`), not in the
  caller's working folder.
- **Launcher tag.** The experiment sees `WAXX_LAUNCHER=kq` and `WAXX_QUEUE_JOB=<id>:<token>`,
  and leaves restarting the monitor to the server.
- **run_lock.py.** After the flip, the agents' `run_lock.py run -- %kpy% & ar <file>` would
  become a queue client. It would hold its lock while the job waits, the run would carry the
  queue's launcher tag instead of `run_lock`, and its Ctrl-C would end only kq.
  - A replacement is staged (not installed) in
    `C:\lab\skynet_log\outputs\wt\kq\skill_scripts\run_lock.py`, with the installed version
    it is based on in `orig\`.
  - It rewrites a command word `ar`, in any case, at the start or after `&` / `&&`, to
    `"%code%\.venv\Scripts\artiq_run.exe" --device-db "%db%"`. That is `ar.lnk`'s own
    target; a bare `artiq_run` would need the venv on PATH.
  - Other shapes are not rewritten: `call ar`, `|| ar`, `(ar ...)`, `"ar"`, `ar.bat`, and
    `ar` elsewhere. For those it prints a warning, and they would go through the queue.
  - It is copied over `.claude/skills/run-experiment/scripts/run_lock.py` at the flip, not
    before.
