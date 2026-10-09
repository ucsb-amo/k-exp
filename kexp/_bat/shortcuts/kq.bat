@echo off
rem kq: the run queue's command line (waxx.util.device_state.kq).  kq --help lists
rem the commands, the job states and the exit codes.  The queue lives in the monitor
rem server; kq never runs an experiment itself.
"%code%\.venv\Scripts\python.exe" -m waxx.util.device_state.kq %*
exit /b %errorlevel%
