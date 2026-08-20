call %kpy%
start "TPI Server" cmd /k python -m beacon.tpi.server
timeout /t 2 /nobreak >nul
python -m beacon.tpi.gui
pause
