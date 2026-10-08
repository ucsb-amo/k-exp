"""Summarize timing_bench runs: per-pulse margin / read latency / posterior time (ns).

    python bench_analyze.py RID [RID ...]

Read-only loads (atomdata, roi_id='auto'). Every pulse of every shot, the first pulse of each shot
excluded from the margin statistics only (its "previous step" is the shot setup, not a feedback
step) -- stated in the output. Writes bench_summary.json (appends per run) next to this script.
"""
import json
import os
import sys

import numpy as np

from kexp import atomdata

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_summary.json")


def q(a, p):
    return float(np.nanpercentile(a, p)) if a.size else float("nan")


def one(rid):
    ad = atomdata(rid, roi_id="auto")
    margin = np.asarray(ad.data.bench_margin, float)
    read = np.asarray(ad.data.bench_read, float)
    post = np.asarray(ad.data.bench_post, float)
    mode = int(np.ravel(ad.p.bench_mode)[0])
    slack = float(np.ravel(ad.p.t_calculation_slack_compensation_mu)[0])
    n_shots, n_p = margin.shape[0], margin.shape[-1]
    # steps never reached (a shot or run cut short by an underflow) keep read == 0: drop them
    filled = read.reshape(n_shots, -1) != 0
    m = margin.reshape(n_shots, -1)[:, 1:][filled[:, 1:]]   # steps 1.. (step 0 follows setup)
    r = read.reshape(n_shots, -1)[filled]
    po = post.reshape(n_shots, -1)[filled]
    written = int(filled.sum())
    print(f"run {rid}: {written} of {filled.size} steps written ({filled.size - written} never reached, dropped)")
    if m.size == 0:
        m = np.array([np.nan])
    res = {"run_id": rid, "mode": mode, "calc_slack_us": slack / 1e3, "shots": int(n_shots),
           "pulses_per_shot": int(n_p), "steps_in_margin_stats": int(m.size),
           "read_values_nonzero": int(written),
           "margin_us": {"min": float(np.min(m)) / 1e3, "p0.1": q(m, 0.1) / 1e3, "p1": q(m, 1) / 1e3,
                         "median": q(m, 50) / 1e3},
           "read_latency_us": {"median": q(r, 50) / 1e3, "p99": q(r, 99) / 1e3, "max": float(np.max(r)) / 1e3},
           "posterior_us": {"median": q(po, 50) / 1e3, "p99": q(po, 99) / 1e3, "max": float(np.max(po)) / 1e3},
           # consumption = slack budget used between the sample and the next deadline
           "stall_like_steps_margin_below_median_minus_10us": int(np.sum(m < q(m, 50) - 10e3))}
    if hasattr(ad.data, "seg_top") and mode >= 1:
        segs = {}
        for name in ("seg_top", "seg_meas", "seg_pre", "seg_prop", "seg_wait"):
            s = np.asarray(getattr(ad.data, name), float).reshape(n_shots, -1)[filled]
            segs[name] = {"median": q(s, 50) / 1e3, "p99": q(s, 99) / 1e3}
        segs["bench_post (weigh)"] = {"median": q(po, 50) / 1e3, "p99": q(po, 99) / 1e3}
        res["cpu_segments_us"] = segs
    print(json.dumps(res, indent=1))
    allres = json.load(open(OUT)) if os.path.exists(OUT) else {}
    allres[str(rid)] = res
    json.dump(allres, open(OUT, "w"), indent=1)


for a in sys.argv[1:]:
    one(int(a))
