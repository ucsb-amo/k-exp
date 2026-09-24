@echo off
rem Server Dashboard: supervises every hardware-owning server on this PC.
rem Launched with pythonw so no console window lingers; everything the
rem servers print lands in the dashboard Log panel and the log files.
call %kpy%
cd %code%\k-exp
start "" pythonw -m kexp.util.dashboard.server_dashboard_app %*
