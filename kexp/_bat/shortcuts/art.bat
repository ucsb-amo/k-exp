@echo off
rem "ar, timed": run an experiment exactly like ar, and print a startup timeline.
rem   art <file>.py [artiq_run args] [--timing-json <path>] [--check-hooks]
rem The timer is generic (waxx); kexp's own host steps come from startup_steps.py.
"%code%\.venv\Scripts\python.exe" "%code%\wax\waxx-src\waxx\util\profiling\startup_timer.py" --host-steps-file "%code%\k-exp\kexp\util\profiling\startup_steps.py" --device-db "%db%" %*
