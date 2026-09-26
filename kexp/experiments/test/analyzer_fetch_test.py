"""RTIO analyzer fetch test (2026-09-26).

Question: does fetching the analyzer buffer (port 1382) while a kernel is still
submitting events lose those events, and how long does a fetch take? The
firmware in our tree disarms recording for the whole transfer (master
runtime/analyzer.rs, satellite satman/analyzer.rs); the Kasli-SoC master runs
artiq-zynq, which is not vendored.

Touches ONLY ttl84 (TTLOut, DRTIO destination 2, unassigned in the TTL frames,
cleared for this test by the user) and the master's RTIO log channel
(rtio_log markers, no physical output). No Base, no liveOD, nothing written to
the run archive. Raw dumps + a summary go to OUT_DIR.

Sequence:
  A_clear  fetch (empties the buffer; holds whatever ran before this kernel)
  train A  N_PULSES pulses on ttl84, an rtio_log marker every LOG_EVERY pulses
  A_after  fetch -> baseline: every pulse must be there; fetch timing with
           ~2*N_PULSES events in destination 2's buffer
  B_clear  fetch
  train B  same train; a host thread fetches (B_mid) T_BG_FETCH after the
           train starts, while the kernel is still submitting
  B_after  fetch -> pulses/markers missing from B_mid + B_after = events
           submitted while recording was off
  E_1..3   back-to-back fetches -> cost of an (almost) empty fetch

End state: ttl84 low (set before the first train and after the last). An
underflow inside a train is caught: ttl84 is set low and the test goes on.
Any other kernel exception leaves ttl84 wherever the train was (unconnected).
"""

from artiq.experiment import *

OUT_DIR = r"G:\Shared drives\Tweezers\Other\skynet_log\outputs\2026-09-26_10-05_analyzer_fetch_test"
ANALYZER_PORT = 1382


class AnalyzerFetchTest(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.ttl = self.get_device("ttl84")

        self.n_pulses = 7000          # 2 events each: 14000 < 16384 per buffer
        self.log_every = 100
        self.t_period = 100.e-6
        self.t_high = 20.e-6
        self.t_lead = 10.e-3          # slack banked before each train
        self.t_bg_fetch = 0.30        # host delay before the mid-train fetch (s)

        self.t_high_mu = self.core.seconds_to_mu(self.t_high)
        self.t_low_mu = self.core.seconds_to_mu(self.t_period - self.t_high)
        self.t_lead_mu = self.core.seconds_to_mu(self.t_lead)
        self.kernel_invariants = {"n_pulses", "log_every", "t_high_mu",
                                  "t_low_mu", "t_lead_mu"}

    def prepare(self):
        self.core_host = self.get_device_db()["core"]["arguments"]["host"]
        self.ttl_channel = self.get_device_db()["ttl84"]["arguments"]["channel"]
        self.dumps = []
        self.t0_mu = {}
        self.underflows = []
        self.notes = []
        self._bg_thread = None
        self._announce_to_monitor()

    # ---------------------------------------------------------------- kernel

    @kernel
    def run(self):
        self.core.reset()
        self.ttl.off()
        self.core.wait_until_mu(now_mu())
        self.fetch("A_clear")
        self.train(0)
        self.fetch("A_after")
        self.fetch("B_clear")
        self.train(1)
        self.join_bg()
        self.fetch("B_after")
        self.core.break_realtime()
        self.ttl.off()
        self.core.wait_until_mu(now_mu())
        self.fetch("E_1")
        self.fetch("E_2")
        self.fetch("E_3")

    @kernel
    def train(self, phase: TInt32):
        self.core.break_realtime()
        delay_mu(self.t_lead_mu)
        t0 = now_mu()
        self.note_t0(phase, t0)
        if phase == 1:
            self.start_bg_fetch()
        try:
            for i in range(self.n_pulses):
                self.ttl.pulse_mu(self.t_high_mu)
                if i % self.log_every == 0:
                    rtio_log("aft", i)
                delay_mu(self.t_low_mu)
        except RTIOUnderflow:
            self.note_underflow(phase)
            self.core.break_realtime()
            self.ttl.off()
        self.core.wait_until_mu(now_mu())

    # ------------------------------------------------------------------ RPCs

    @rpc(flags={"async"})
    def note_t0(self, phase: TInt32, t0: TInt64):
        import time
        self.t0_mu[int(phase)] = int(t0)
        self.notes.append((f"t0 phase {int(phase)} received", time.perf_counter()))

    @rpc(flags={"async"})
    def note_underflow(self, phase: TInt32):
        self.underflows.append(int(phase))

    @rpc(flags={"async"})
    def start_bg_fetch(self):
        import threading
        import time
        self.notes.append(("bg fetch thread start", time.perf_counter()))

        def _bg():
            time.sleep(self.t_bg_fetch)
            self.fetch("B_mid")

        self._bg_thread = threading.Thread(target=_bg, daemon=True)
        self._bg_thread.start()

    def join_bg(self) -> TNone:
        if self._bg_thread is not None:
            self._bg_thread.join(timeout=30.)

    def fetch(self, label) -> TNone:
        """Read the whole analyzer dump. Never raises into the kernel."""
        import socket
        import time
        rec = {"label": label, "t_wall": time.time(), "p_start": time.perf_counter(),
               "err": "", "data": b""}
        try:
            with socket.create_connection((self.core_host, ANALYZER_PORT), timeout=10.) as s:
                rec["p_connected"] = time.perf_counter()
                chunks = []
                first = True
                while True:
                    b = s.recv(65536)
                    if first and b:
                        rec["p_first_byte"] = time.perf_counter()
                        first = False
                    if not b:
                        break
                    chunks.append(b)
            rec["data"] = b"".join(chunks)
        except Exception as e:
            rec["err"] = repr(e)
        rec["p_end"] = time.perf_counter()
        self.dumps.append(rec)

    # --------------------------------------------------------------- monitor

    def _announce_to_monitor(self):
        import atexit
        import uuid
        self._token = uuid.uuid4().hex
        self._mon = None
        try:
            from waxx.util.comms_server.comm_client import MonitorClient
            self._mon = MonitorClient()
            print("[monitor] status before:", self._mon.get_status())
            print("[monitor] announce:", self._mon.announce_run(
                run_id=None, expt="analyzer_fetch_test", client="kong", token=self._token))
            atexit.register(self._withdraw)
        except Exception as e:
            print(f"[monitor] could not announce ({e!r}); composite ops not fenced")

    def _withdraw(self):
        try:
            if self._mon is not None:
                self._mon.withdraw_run(self._token)
        except Exception:
            pass

    # --------------------------------------------------------------- analyze

    def analyze(self):
        import os
        import json
        try:
            # raw bytes first, exactly as received: the analysis below must not
            # be able to lose them
            os.makedirs(OUT_DIR, exist_ok=True)
            for rec in self.dumps:
                with open(os.path.join(OUT_DIR, f"{rec['label']}.dump"), "wb") as f:
                    f.write(rec["data"])
            with open(os.path.join(OUT_DIR, "fetch_log.json"), "w") as f:
                json.dump([{k: v for k, v in rec.items() if k != "data"}
                           for rec in self.dumps], f, indent=1, default=str)
            summary = self._summarize()
            with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
                json.dump(summary, f, indent=1, default=str)
            print(json.dumps(summary, indent=1, default=str))
        finally:
            if self._mon is not None:
                try:
                    print("[monitor] restart (run complete):", self._mon.send_end())
                    self._withdraw()
                except Exception as e:
                    print(f"[monitor] could not signal the end ({e!r}); restart it by hand")

    def _summarize(self):
        import struct
        from collections import Counter
        from artiq.coredevice.comm_analyzer import (decode_dump, OutputMessage,
                                                    InputMessage, ExceptionMessage,
                                                    StoppedMessage)
        period_mu = int(self.t_high_mu + self.t_low_mu)
        p_ref = min(r["p_start"] for r in self.dumps) if self.dumps else 0.
        out = {"core_host": self.core_host, "ttl84_channel": self.ttl_channel,
               "n_pulses": self.n_pulses, "period_mu": period_mu,
               "t0_mu": self.t0_mu, "underflows": self.underflows,
               "notes": [(n, p - p_ref) for n, p in self.notes], "fetches": []}
        pulses = {}
        markers = {}
        for rec in self.dumps:
            d = {"label": rec["label"], "err": rec["err"], "nbytes": len(rec["data"]),
                 "t_start_s": rec["p_start"] - p_ref,
                 "dt_total_ms": 1e3 * (rec["p_end"] - rec["p_start"])}
            if "p_connected" in rec:
                d["dt_connect_ms"] = 1e3 * (rec["p_connected"] - rec["p_start"])
            if "p_first_byte" in rec:
                d["dt_first_byte_ms"] = 1e3 * (rec["p_first_byte"] - rec["p_start"])
            data = rec["data"]
            if data:
                endian = ">" if data[0:1] == b"E" else "<"
                sent, total, err_flag, log_ch, onehot = struct.unpack(endian + "IQbbb", data[1:16])
                d["header"] = {"sent_bytes": sent, "total_byte_count": total,
                               "error_occurred": err_flag, "log_channel": log_ch}
                try:
                    dump = decode_dump(data)
                except Exception as e:
                    d["decode_err"] = repr(e)
                    out["fetches"].append(d)
                    continue
                msgs = dump.messages
                per_dest = Counter()
                exc = []
                n_stopped = 0
                ttl_rise, ttl_fall = [], []
                ttl_cnt = []
                log_text, log_ts, log_cnt = "", [], []
                for m in msgs:
                    if isinstance(m, StoppedMessage):
                        n_stopped += 1
                        continue
                    if isinstance(m, ExceptionMessage):
                        exc.append((m.channel, m.rtio_counter, str(m.exception_type)))
                        continue
                    per_dest[m.channel >> 16] += 1
                    if isinstance(m, OutputMessage) and m.channel == self.ttl_channel and m.address == 0:
                        (ttl_rise if m.data else ttl_fall).append(m.timestamp)
                        ttl_cnt.append(m.rtio_counter)
                    if isinstance(m, OutputMessage) and m.channel == dump.log_channel:
                        for k in range(4):
                            c = (m.data >> (24 - 8 * k)) & 0xff
                            if c:
                                log_text += chr(c)
                        log_ts.append(m.timestamp)
                        log_cnt.append(m.rtio_counter)
                d["n_messages"] = len(msgs)
                d["events_per_destination"] = dict(per_dest)
                d["exceptions"] = exc
                d["n_stopped"] = n_stopped
                d["ttl84_rising"] = len(ttl_rise)
                d["ttl84_falling"] = len(ttl_fall)
                if ttl_cnt:
                    d["ttl84_submit_counter_range_mu"] = [min(ttl_cnt), max(ttl_cnt)]
                if log_cnt:
                    d["log_submit_counter_range_mu"] = [min(log_cnt), max(log_cnt)]
                # pulse indices against the train they belong to
                phase = 0 if rec["label"].startswith("A") else 1 if rec["label"].startswith("B") else None
                if phase is not None and phase in self.t0_mu:
                    t0 = self.t0_mu[phase]
                    idx, off_grid = [], 0
                    for ts in ttl_rise:
                        q, r = divmod(ts - t0, period_mu)
                        if r:
                            off_grid += 1
                        else:
                            idx.append(q)
                    pulses.setdefault(phase, {})[rec["label"]] = sorted(idx)
                    d["ttl84_pulse_index_range"] = [min(idx), max(idx)] if idx else None
                    d["ttl84_off_grid"] = off_grid
                    mk = []
                    for part in log_text.split("\x1d"):
                        if "\x1e" in part:
                            name, msg = part.split("\x1e", 1)
                            if name.endswith("aft"):
                                try:
                                    mk.append(int(msg.strip().split()[-1]))
                                except ValueError:
                                    pass
                    markers.setdefault(phase, {})[rec["label"]] = mk
                    d["markers"] = [min(mk), max(mk), len(mk)] if mk else None
            out["fetches"].append(d)

        expected = set(range(self.n_pulses))
        expected_mk = set(range(0, self.n_pulses, self.log_every))
        for phase, name in ((0, "A"), (1, "B")):
            got = set()
            for v in pulses.get(phase, {}).values():
                got |= set(v)
            got_mk = set()
            for v in markers.get(phase, {}).values():
                got_mk |= set(v)
            miss = sorted(expected - got)
            miss_mk = sorted(expected_mk - got_mk)
            out[f"train_{name}"] = {
                "pulses_recorded": len(got), "pulses_missing": len(miss),
                "missing_pulse_index_range": [miss[0], miss[-1]] if miss else None,
                "markers_recorded": len(got_mk), "markers_missing": len(miss_mk),
                "missing_marker_range": [miss_mk[0], miss_mk[-1]] if miss_mk else None,
            }
        return out
