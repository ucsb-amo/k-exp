"""How many RTIO events does one hf_tweezer_bec shot put on each device?
(2026-09-26, for sizing per-shot RTIO analyzer recording.)

A copy of default_experiments/hf_tweezer_bec.py (as of aea22be5) with:
  - t_tof = 2 ms, N_repeats = 1 (one shot) -- the user's request;
  - analyzer fetches (port 1382), each inside a host call the kernel is
    blocked in, so nothing is submitted while the analyzer is disarmed:
      pre_run   top of run(), before init_kernel    (clears the buffer)
      preamble  first _check_for_abort_signal()      (init_kernel, 2D MOT,
                                                      the 4 warm-up shots)
      shot0     _notify_shot_complete()              (init_scan_kernel ..
                                                      cleanup_scan_kernel)
      tail      analyze(), before end()              (post_scan)
Everything else is hf_tweezer_bec as written (warm-ups, camera, save_data,
restart_monitor=False). Raw dumps + summary go to OUT_DIR.
"""

import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras, Adjust

OUT_DIR = r"C:\lab\skynet_log\outputs\2026-09-26_10-05_hf_bec_event_count"
ANALYZER_PORT = 1382


class hf_bec_event_count(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=4)

        self.p.t_mot_load = 1.0
        self.p.t_tweezer_hold = 100.e-3

        self.p.t_tof = 2.e-3          # user request (file: 20 us)

        self.data.apd = self.data.add_data_container(1)

        self.p.N_repeats = 1          # user request (file: 5)

        self._rtio_dumps = []
        self._rtio_abort_checks = 0
        self._rtio_host = self.get_device_db()["core"]["arguments"]["host"]

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()

    @kernel
    def run(self):
        self.rtio_fetch("pre_run")
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    # ------------------------------------------------ analyzer fetch points

    def rtio_fetch(self, label) -> TNone:
        """Read the whole analyzer dump. Never raises."""
        import socket
        import time
        rec = {"label": label, "p_start": time.perf_counter(), "err": "", "data": b""}
        try:
            with socket.create_connection((self._rtio_host, ANALYZER_PORT), timeout=10.) as s:
                chunks = []
                while True:
                    b = s.recv(65536)
                    if not b:
                        break
                    chunks.append(b)
            rec["data"] = b"".join(chunks)
        except Exception as e:
            rec["err"] = repr(e)
        rec["p_end"] = time.perf_counter()
        self._rtio_dumps.append(rec)
        # to disk now: an exception later in the run must not lose the dump
        # (run 83110 lost its breakdown because only analyze() wrote them)
        try:
            import os
            out = os.path.join(OUT_DIR, f"run_{self.run_info.run_id}")
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, f"{label}.dump"), "wb") as f:
                f.write(rec["data"])
        except Exception as e:
            print(f"[rtio] could not write {label}.dump: {e!r}")
        print(f"[rtio] {label}: {len(rec['data'])} B in "
              f"{1e3 * (rec['p_end'] - rec['p_start']):.0f} ms {rec['err']}")

    def _check_for_abort_signal(self, raise_error=True) -> bool:
        if self._rtio_abort_checks == 0:
            self.rtio_fetch("preamble")
        self._rtio_abort_checks += 1
        return super()._check_for_abort_signal(raise_error)

    def _notify_shot_complete(self):
        self.rtio_fetch(f"shot{self._shot_complete_count}")
        return super()._notify_shot_complete()

    # ------------------------------------------------------------ analysis

    def analyze(self):
        import os
        self.rtio_fetch("tail")
        try:
            self._rtio_save()
        except Exception as e:
            print(f"[rtio] summary failed: {e!r} (raw dumps written first)")
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, restart_monitor=False)

    def _rtio_save(self):
        import os
        import json
        # one subfolder per run (run 83109's files sit directly in OUT_DIR);
        # the dumps themselves were written by rtio_fetch as they arrived
        out = os.path.join(OUT_DIR, f"run_{self.run_info.run_id}")
        os.makedirs(out, exist_ok=True)
        summary = {"run_id": self.run_info.run_id, "fetches": [self._rtio_summ(r) for r in self._rtio_dumps]}
        with open(os.path.join(out, "summary.json"), "w") as f:
            json.dump(summary, f, indent=1, default=str)
        for d in summary["fetches"]:
            print(json.dumps({k: v for k, v in d.items() if k != "top_channels"}, default=str))
            print("   top channels:", d.get("top_channels"))

    def _rtio_summ(self, rec):
        import struct
        from collections import Counter
        from artiq.coredevice.comm_analyzer import (decode_dump, OutputMessage, InputMessage,
                                                    ExceptionMessage, StoppedMessage)
        d = {"label": rec["label"], "err": rec["err"], "nbytes": len(rec["data"]),
             "dt_ms": round(1e3 * (rec["p_end"] - rec["p_start"]), 1)}
        data = rec["data"]
        if not data:
            return d
        endian = ">" if data[0:1] == b"E" else "<"
        sent, total, err_flag, log_ch, _ = struct.unpack(endian + "IQbbb", data[1:16])
        d["header"] = {"sent_bytes": sent, "total_byte_count": total, "error_occurred": err_flag}
        dump = decode_dump(data)
        names = {}
        for k, v in self.get_device_db().items():
            if isinstance(v, dict) and "channel" in v.get("arguments", {}):
                names[v["arguments"]["channel"]] = k
        for key, obj in vars(self.ttl).items():
            ch = getattr(obj, "ch", None)
            if isinstance(ch, (int, np.integer)) and not key.startswith("_"):
                full = getattr(getattr(obj, "ttl_device", None), "channel", None)
                if full is not None:
                    names[int(full)] = f"{names.get(int(full), '')}={key}"
        per_dest, per_ch = Counter(), Counter()
        n_in, exc, ts, slack = 0, [], [], []
        for m in dump.messages:
            if isinstance(m, StoppedMessage):
                continue
            if isinstance(m, ExceptionMessage):
                exc.append((names.get(m.channel, m.channel), str(m.exception_type)))
                continue
            per_dest[m.channel >> 16] += 1
            per_ch[m.channel] += 1
            if isinstance(m, InputMessage):
                n_in += 1
            else:
                ts.append(m.timestamp)
                slack.append(m.timestamp - m.rtio_counter)
        d["events_per_destination"] = dict(per_dest)
        d["destinations_full_ring"] = [k for k, v in per_dest.items() if v >= 16383]
        d["n_input_events"] = n_in
        d["exceptions"] = exc
        if ts:
            d["timeline_span_s"] = (max(ts) - min(ts)) * 1e-9
            d["min_slack_us"] = min(slack) * 1e-3
        d["top_channels"] = [(names.get(ch, ch), n) for ch, n in per_ch.most_common(25)]
        return d
