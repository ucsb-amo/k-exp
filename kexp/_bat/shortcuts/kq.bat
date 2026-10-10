@echo off
rem kq: the run queue's command line (waxx.util.device_state.kq).  kq --help lists
rem the commands, the job states and the exit codes.  The queue lives in the monitor
rem server; kq never runs an experiment itself.  A terminal convenience: after a Ctrl-C
rem cmd's "Terminate batch job (Y/N)?" can lose the exit code; scripts use kq.exe.
"%code%\.venv\Scripts\python.exe" -m waxx.util.device_state.kq %*
exit /b %errorlevel%
