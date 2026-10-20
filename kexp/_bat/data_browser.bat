@echo off
rem Data Browser. Reopens itself in a fresh console first: a console opened from
rem a shortcut (Data Browser.lnk) is tied to that shortcut on the taskbar and can
rem stay off the shared terminals button even with its ID set (waxa.taskbar).
if not "%~1"=="--console" (
    start "Data Browser" "%ComSpec%" /c ""%~f0" --console"
    exit /b
)
call %kpy%
cd /d %code%\k-exp
python %code%\k-exp\kexp\util\data_browser\data_browser.py
