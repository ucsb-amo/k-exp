@echo off
rem Client Dashboard: embeds the control GUIs; starts no servers.
call %kpy%
cd %code%\k-exp
start "" pythonw -m kexp.util.dashboard.client_dashboard_app %*
