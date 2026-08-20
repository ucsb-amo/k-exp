call %kpy%
start "Basler Server" cmd /k python -m beacon.basler.server_gui
timeout /t 2 /nobreak >nul
python -m beacon.basler.gui
pause
