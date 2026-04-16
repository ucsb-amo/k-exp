@echo off
setlocal

set "scriptsDir=%USERPROFILE%\.tray_launcher\scripts"

if not exist "%scriptsDir%\" (
    echo Scripts directory not found: "%scriptsDir%"
    exit /b 1
)

for %%F in ("%scriptsDir%\*") do (
    if not exist "%%~fF\" (
        echo Terminating launcher script: %%~nF
        launcher terminate "%%~nF"
    )
)

endlocal