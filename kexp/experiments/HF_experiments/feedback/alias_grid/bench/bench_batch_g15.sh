#!/bin/bash
# usage: bench_batch_g15.sh "SLACK_US SLACK_US ..."   (fast path = BENCH_MODE 2, grid 15, 200 pulses x 3 shots each)
# Each run goes through the run lock (hardware-run prompt per launch); analysis appended to logs/bench_g15.log
D=/c/lab/skynet_log/outputs/2026-10-07_13-38_aliasing_analysis
cd /c/Users/jarjarbinks/code
for slack in $1; do
  echo "=== BENCH grid 15 mode 2 slack $slack us  $(date +%H:%M:%S) ===" | tee -a "$D/logs/bench_g15.log"
  BENCH_MODE=2 BENCH_GRID=15 BENCH_SLACK_US=$slack BENCH_PULSES=200 BENCH_SHOTS=3 \
    uv run python .claude/skills/run-experiment/scripts/run_lock.py run --expt timing_bench_g15 -- "%kpy% & ar C:\lab\skynet_log\outputs\2026-10-07_13-38_aliasing_analysis\expts\timing_bench_g15.py" 2>&1 \
    | grep -v ": float,$\|: numpy.array\|: numpy.int64,$\|: bool,$\|: str,$\|: int32,$\|: int64,$\|: numpy.int32,$" | tee -a "$D/logs/bench_g15.log"
  rid=$(grep -o "Run ID: [0-9]*" "$D/logs/bench_g15.log" | tail -1 | awk '{print $3}')
  echo "BENCH slack $slack -> run $rid" | tee -a "$D/logs/bench_g15.log"
  uv run python "$D/bench_analyze.py" $rid 2>&1 | grep -v "atomdata timing" | tee -a "$D/logs/bench_g15.log"
done
echo BATCH_DONE | tee -a "$D/logs/bench_g15.log"
