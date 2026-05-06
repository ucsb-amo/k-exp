@echo off
call %kpy%
setlocal

set "SCRIPTS_DIR=%USERPROFILE%\.tray_launcher\scripts"

for %%F in ("%SCRIPTS_DIR%\*.bat") do (
    launcher start "%%~nxF"
)

endlocal
pause