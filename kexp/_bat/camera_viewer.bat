REM Camera Viewer: every camera on the lab network (Basler servers, liveOD), one dock each.
REM Viewer only -- no camera server (basler_gui.bat also starts a Basler server).
call %kpy%
python -m kexp.util.guis.basler.camera_viewer_app
