@echo off
rem "ar, timed": run an experiment exactly like ar, and print a startup timeline.
rem   art <file>.py [artiq_run args] [--timing-json <path>] [--check-hooks]
"%code%\.venv\Scripts\python.exe" "%code%\k-exp\kexp\util\profiling\startup_timer.py" --device-db "%db%" %*
