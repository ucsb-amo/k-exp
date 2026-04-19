@echo off
call %kpy%
cd /d %code%\k-exp
python %code%\k-exp\kexp\util\data_browser\data_browser.py
pause
