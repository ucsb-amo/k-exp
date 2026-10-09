@echo off
rem ar through the run queue: ar_queue <file>.py [key=value ...] [kq run options] [-- argv]
rem = kq run: submit to the monitor server's queue, print the run's output as artiq_run
rem would, exit with the run's result.  Refuses (exit 4) when no queue is beaconing.
rem The direct path, outside the queue, stays: artiq_run --device-db %db% <file>.py
"%code%\.venv\Scripts\python.exe" -m waxx.util.device_state.kq run %*
exit /b %errorlevel%
