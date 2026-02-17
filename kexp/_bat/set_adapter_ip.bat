@echo off
REM Batch file wrapper for set_adapter_ip.ps1
REM This script configures Ethernet adapter IPv4 settings based on MAC address mappings
REM Requires Administrator privileges

setlocal enabledelayedexpansion

REM Check if running as Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Requesting Administrator privileges...
    echo.
    
    REM Re-run as Administrator using PowerShell
    powershell -Command "Start-Process cmd -ArgumentList '/c %~f0' -Verb RunAs"
    exit /b
)

REM Define the EthernetConfig directory
set "configDir=C:\ProgramData\EthernetConfig"

REM Check if the PowerShell script exists
if not exist "%configDir%\set_adapter_ip.ps1" (
    color 0C
    echo.
    echo ERROR: set_adapter_ip.ps1 not found in %configDir%
    echo.
    pause
    exit /b 1
)

REM Check if LAN_devices.csv exists
if not exist "%configDir%\LAN_devices.csv" (
    color 0C
    echo.
    echo ERROR: LAN_devices.csv not found in %configDir%
    echo.
    pause
    exit /b 1
)

REM Run the PowerShell script with administrator privileges
echo Running set_adapter_ip.ps1 from %configDir%...
echo.

REM Execute the PowerShell script
powershell -NoProfile -ExecutionPolicy Bypass -File "%configDir%\set_adapter_ip.ps1"

if %errorlevel% neq 0 (
    color 0C
    echo.
    echo Script completed with errors.
    echo.
    pause
) else (
    color 0A
    echo.
    echo Script completed successfully.
    echo.
    pause
)

exit /b %errorlevel%
