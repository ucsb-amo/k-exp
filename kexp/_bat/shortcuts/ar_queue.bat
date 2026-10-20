@echo off
rem ar through the run queue: ar_queue <file>.py [key=value ...] [kq run options] [-- argv]
rem = kq run: submit to the monitor server's queue, print the run's output as artiq_run
rem would, exit with the run's result.  Refuses (exit 4) when no queue is beaconing.
rem The direct path, outside the queue, stays: artiq_run --device-db %db% <file>.py
rem A terminal convenience only: after a Ctrl-C cmd asks "Terminate batch job (Y/N)?" and
rem the exit code can be lost.  Point ar at .venv\Scripts\kq.exe run instead (README.md).
"%code%\.venv\Scripts\python.exe" -m waxx.util.device_state.kq run %*
exit /b %errorlevel%
