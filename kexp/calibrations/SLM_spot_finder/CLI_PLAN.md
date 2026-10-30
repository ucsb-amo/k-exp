# SLM spot finder CLI — plan (2026-10-24, not built)

A command-line front end to the SLM spot finder: the same scan, run gate, frame sources and SLM
controller as `SLM_andor_main_gui.py`, with no Qt windows. Usable from a terminal by a person and
scriptable by an agent; every result lands in a file instead of a preview dialog.

**Andor policy (lab-rules §2 exception, 2026-10-24):** this CLI is an acceptable program for
opening the Andor directly (`--direct`), but only when the user specifically asks for that.
Without that ask it takes frames through liveOD's camera host (`--stream`, the CLI's default)
or opens nothing. The GUI's `auto` fallback to opening the Andor is deliberately not the CLI's
default. Through `--stream`, agents may run `goto` / `snap` / `scan` without asking (user,
2026-10-24).

---

## Commands

```
spot_finder_cli.py status [--json]
spot_finder_cli.py goto CX CY [--mode spot|grating] [pattern options]
spot_finder_cli.py snap [--out DIR] [camera options] [source options]
spot_finder_cli.py scan [--center CX CY] --radius R --step S [--settle-ms 150]
                        [camera options] [source options] [pattern options]
                        [--trigger] [--return] [--dry-run] [--out DIR] [--json]
```

| Option group | Options |
|---|---|
| source | `--stream` (default: liveOD's Andor or nothing), `--direct` (borrow the Andor from liveOD if it holds it, then open it here, `ServedAndorSource`; only on a specific ask) |
| camera | `--exposure S`, `--gain G`, `--shutter open\|closed` — applied through the source; what the camera actually applied (clamps) is printed and saved |
| pattern | `--spot-radius`, `--grating-size`, `--grating-spacing`, `--angle-deg` |
| scan | `--center` defaults to `ExptParams.px_slm_phase_mask_position_x/y` (what `SLMController` starts from) |

- **`status`** (read-only, writes nothing anywhere): liveOD run gate (`RunGate.poll_once`), SLM
  server link and whether it confirms patterns (`check_link`, sends no pattern), which Andor source
  would be used (`choose_source(mode)`, never opens a camera), APD stage position
  (`APDStageClient.position()`, never moves), the default center.
- **`goto`**: one gated `set_center_and_wait`; prints confirmed / unconfirmed and the server's apply time.
- **`snap`**: one frame at the current pattern (`begin_scan` → `snap` → `end_scan`), saved raw.
- **`scan`**: the GUI's `start_scan` without the dialogs — `scan_grid` → `run_scan` (called directly in
  the main thread, not through the `ScanWorker` QThread) → save. One progress line per position.
  `--dry-run` prints the grid, point count, estimated time and the source that would be used, and
  touches neither the SLM nor the camera.

**Exit codes:** 0 complete; 1 ended early (stopped, preempted by a run, camera failures) — data
saved; 2 refused before anything was written (gate closed, no camera, APD stage in, liveOD
refused to lend the Andor, `DeviceBusy`); 3 error.

---

## Behaviour that must match the GUI

- **Run gate:** the same `RunGate` + `CombinedGate(run_gate, source)` the window builds, asked before
  every SLM write. Fails closed. `--wait-for-gate SECONDS` waits for the gate to open instead of
  refusing; never longer than that.
- **APD stage IN:** the GUI asks "scan anyway?". The CLI refuses (exit 2) unless
  `--ignore-apd-stage`. It never moves the stage.
- **No automatic return:** the scan leaves the pattern where it last wrote it, as the GUI does (a
  deferred write could land in a run). The final line says where it is and where it started;
  `--return` sends it back once, gated, right after the scan.
- **Run takes the camera mid-scan (`Preempted`):** the scan ends, the position in flight is blank,
  no further SLM write; exit 1 with what is saved.
- **`--direct` borrows the Andor from liveOD** (user, 2026-10-24) instead of needing a person to
  release it first. The mechanism already exists in the other direction: liveOD's camera host
  (`waxx/util/live_od/camera_host/host.py`, `_h_relinquish`) accepts `RELINQUISH_CAMERA{camera_ids,
  holder, ttl_s}` from programs on this PC (its `write_policy` refuses other PCs). It closes the
  Andor with a verified close and keeps it reserved for the holder. It refuses (`run_locked`) while a
  run holds the camera. Steps:
  1. `choose_source("stream")`'s directory lookup finds liveOD's host and the Andor's `camera_id`.
  2. Send RELINQUISH with holder `{label: "spot finder CLI", host, pid}`. Refused → exit 2 with
     liveOD's reason. Renew every `ttl_s / 3`: reuse `claims.ReservationKeeper` or a small loop.
  3. Open with `ServedAndorSource`, served as `camera_server:<host>:spot_finder_cli` under liveOD's
     camera id, so liveOD's `_claim_if_needed` can take it back for a run, as with the GUI.
  4. Teardown: close the Andor, stop the renewals, then `RETURN_CAMERA{camera_ids, holder_id}`.
     liveOD reopens it only if it had it open before. If the CLI dies without returning it, the
     reservation lapses after its TTL (`beacon.camera.reservations.DEFAULT_TTL_S`).
  - **To verify in the build (not known now):** whether liveOD, while its own core still holds a
    reservation for the CLI, can take the Andor back from the CLI's server for an INIT_RUN. A run
    must never be refused because the CLI borrowed the camera. If that fails, the CLI must return
    the reservation as soon as it sees `run_in_progress` (the run gate already polls it), before
    INIT_RUN's camera claim times out. Test both with fakes before kong.
  - The lend applies to `--direct` only, so it needs the same specific ask.
- **liveOD takes over a `--direct` Andor** (`on_handover`): the scan ends as preempted. The CLI
  does not follow the camera to liveOD; it reports and exits.
- **`--trigger`:** only with `--direct` (the served source; `StreamSource` refuses). Never falls back
  to snaps silently. Prints `trigger_summary(last_trigger_report)` and the pulser notes.
  `TTLPulser` announces to the monitor server like a run (the monitor drops and restarts).
- **Ctrl+C:** first one = stop after the current position (`should_stop`), then the normal
  teardown and save. Second one = skip the save, still tear down.
- **Teardown in every path** (`try/finally`, the order of `closeEvent`): `end_scan` → `stop_video` →
  `source.close()` → `shutdown()` the own served Andor → stop renewals + `RETURN_CAMERA` to liveOD
  (if borrowed) → `pulser.close()` → `slm.close()` → `run_gate.stop()`. After a `--direct`
  session, liveOD has the Andor back.

---

## Output (raw, nothing derived written as raw)

`--out DIR` gets `<YYYY-MM-DD_HH-MM-SS>_spot_scan/`. Default for everyone, people and agents:
`C:\lab\skynet_log\outputs\` (user, 2026-10-24), local to kong:

- `frames.npz` — `frames (ny, nx, H, W)` as taken (camera dtype), `has_frame (ny, nx)` bool,
  `xs`, `ys`, `index (ny, nx)` (order taken). Missing tiles are zero **and** `has_frame=False`;
  never read a tile without the mask.
- `scan.json` — every `ScanShot` (point, `slm_applied`, all timestamps, `server_apply_s`, error),
  the outcome string, counts (taken / missing / not reached / unconfirmed), the request (center,
  R, step, settle, pattern params, exposure, gain) and what the camera applied, the source kind and
  banner, gate state at start, trigger report, APD stage position, host, `spot_finder_cli` git
  commit + dirty flag of k-exp.
- `mosaic.png` — the tiles with a red X over each missing one and a note line (as `FinalScanPreviewDialog`).

Never written to `%data%` (that is run data). A summary such as the brightest tile is labelled as
derived and goes in `summary.json`, next to the raw frames — not part of phase 1.

---

## Code changes

1. **`sources.py` (new, Qt-free):** move `make_own_andor_source`, `andor_readout_params`,
   `andor_camera_id`, `open_local_andor`, `make_trigger_pulser` out of `SLM_andor_main_gui.py`; the GUI
   imports them from there (same names, no behaviour change). The GUI module imports pyqtgraph and
   widgets; the CLI must not need them.
2. **`spot_finder_cli.py` (new)**, plus `spot_finder_cli.bat` (`call %kpy%`, `python
   spot_finder_cli.py %*`, like `spot_finder.bat`). Plain `argparse`, no Qt app. `SLMController` is a
   `QObject` with signals: emitted without connections they are no-ops, so it works without an event
   loop — the CLI reads its state and results directly and checks this in tests. `frame_source.py`
   uses `QtCore` only for a connection type; importing `QtCore` without an app is fine.
3. **No `lab_guard` change:** the CLI's path and command line contain no device token. The
   "only when asked" condition for `--direct` is a rule (lab-rules §2), not a hook.

## Tests (offline, `k-exp/tests/test_spot_finder_cli.py`)

Reuse the fakes from `test_spot_finder_scan.py` / `test_spot_finder_trigger.py` (fake sources, the
real `run_server` handler on localhost, fake gate). Cover: exit codes; gate closed → nothing sent;
`Preempted` mid-scan → blank position, no further write, data saved; Ctrl+C → stop after the current
position; teardown order in every path including exceptions; `--stream` never builds a local source;
`--trigger` without `--direct` refused; `has_frame` mask correct; `--dry-run` sends nothing;
lend: refused during a run → exit 2 and nothing opened, RETURN sent on every exit path, renewals
stop, and a fake liveOD host can take the Andor back for a run while the CLI holds it.
No real camera, no UDP 50099 beacons (`dev-machine-is-kong` rules). Run by the test file's path.

## Phases

1. `sources.py` extraction; existing spot finder tests pass unchanged.
2. `status` + `scan --dry-run` (read-only).
3. `goto`, `snap`, `scan` through `--stream`; output files; tests.
4. `--direct`: borrow from liveOD, open, return; handover; then `--trigger`.
5. Docs: wiki `SLM-spot-finder---run-gate.md` (CLI section), AGENTS.md one line.
6. On kong: `status`, `scan --dry-run`, then a small `--stream` scan between runs (an agent may do
   these without asking). `--direct` only when the user asks for it.

## Decisions (user, 2026-10-24)

1. Default output: `C:\lab\skynet_log\outputs\`.
2. Agents may run `goto` / `snap` / `scan` through `--stream` without asking.
3. `--direct` may ask liveOD's camera host to lend the Andor (above).
4. No `--show` window: command line and PNG only.
