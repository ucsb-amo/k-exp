import sys
import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
from artiq.language.environment import EnvExperiment

from waxx.control import AndorEMCCD, DummyCamera

class CameraWorker(QtCore.QThread):
    new_frame_sig = QtCore.pyqtSignal(np.ndarray)
    
    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False

    def run(self):
        self.running = True
        try:
            # Clear any old data
            self.camera.clear_acquisition()
            self.camera.start_acquisition()
            while self.running:
                try:
                    # pylablib wait_for_frame check
                    if self.camera.wait_for_frame(timeout=0.2): 
                        # Grab images as numpy array
                        frames = self.camera.read_multiple_images(return_info=False)
                        if frames is not None and len(frames) > 0:
                            # Send the latest frame
                            data = np.asanyarray(frames[-1], dtype=np.uint16)
                            self.new_frame_sig.emit(data)
                except Exception:
                    continue
        finally:
            try:
                self.camera.stop_acquisition()
            except:
                pass

    def stop(self):
        self.running = False
        self.wait()

class AndorCameraGUI(QtWidgets.QMainWindow):
    def __init__(self, camera):
        super().__init__()
        self.setWindowTitle("Andor EMCCD Preview")
        self.resize(1100, 800)
        self.camera = camera
        
        # Initialize thread
        self.worker = CameraWorker(self.camera)
        self.worker.new_frame_sig.connect(self.update_plot)
        
        # Reset hardware to the specific 'cont' mode requested by your lib
        self.reset_camera_state()
        self.init_ui()

    def reset_camera_state(self):
        """Forces the camera into Internal Trigger / Continuous mode."""
        if isinstance(self.camera, DummyCamera): return
        
        try:
            self.camera.stop_acquisition()
            self.camera.set_trigger_mode("int")
            # Changed from 'run_till_abort' to 'cont' based on your error log
            self.camera.set_acquisition_mode("cont") 
            self.camera.set_read_mode("image")
            # Match your notebook: gain=0., hs=0, vs=0
            self.camera.set_EMCCD_gain(0)
            self.camera.set_hsspeed(0, 0) 
            self.camera.set_vsspeed(0)
            print("Camera state reset to 'cont' mode for Live View.")
        except Exception as e:
            print(f"Warning during reset: {e}")

    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QHBoxLayout(central_widget)

        # Sidebar
        controls = QtWidgets.QVBoxLayout()
        
        self.video_btn = QtWidgets.QPushButton("Start Video")
        self.video_btn.setCheckable(True)
        self.video_btn.clicked.connect(self.toggle_video)
        controls.addWidget(self.video_btn)

        self.shutter_btn = QtWidgets.QPushButton("Open Shutter")
        self.shutter_btn.setCheckable(True)
        self.shutter_btn.clicked.connect(self.safe_shutter)
        controls.addWidget(self.shutter_btn)

        # Params
        controls.addWidget(QtWidgets.QLabel("Exposure (s):"))
        self.exp_spin = QtWidgets.QDoubleSpinBox()
        self.exp_spin.setRange(0.001, 5.0)
        self.exp_spin.setValue(0.05)
        self.exp_spin.editingFinished.connect(self.safe_update_params) 
        controls.addWidget(self.exp_spin)

        controls.addWidget(QtWidgets.QLabel("EM Gain:"))
        self.gain_spin = QtWidgets.QDoubleSpinBox()
        self.gain_spin.setRange(0, 300)
        self.gain_spin.setValue(0.0)
        self.gain_spin.editingFinished.connect(self.safe_update_params)
        controls.addWidget(self.gain_spin)

        self.autolevel_cb = QtWidgets.QCheckBox("Auto-Level Contrast")
        self.autolevel_cb.setChecked(True)
        controls.addWidget(self.autolevel_cb)

        controls.addStretch()
        layout.addLayout(controls, 1)

        # Plot
        self.view = pg.GraphicsLayoutWidget()
        self.plot = self.view.addPlot()
        self.img = pg.ImageItem()
        self.plot.addItem(self.img)
        
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.img)
        self.view.addItem(self.hist)
        layout.addWidget(self.view, 5)

    def _execute_safe_command(self, func, *args, **kwargs):
        was_running = self.worker.isRunning()
        if was_running: self.worker.stop()
        try:
            func(*args, **kwargs)
        except Exception as e:
            print(f"Hardware Error: {e}")
        if was_running: self.worker.start()

    def toggle_video(self, checked):
        if checked:
            self.video_btn.setText("Stop Video")
            self.worker.start()
        else:
            self.video_btn.setText("Start Video")
            self.worker.stop()

    def safe_shutter(self, checked):
        mode = "open" if checked else "closed"
        self._execute_safe_command(self.camera.setup_shutter, mode=mode)
        self.shutter_btn.setText("Close Shutter" if checked else "Open Shutter")

    def safe_update_params(self):
        def update_logic():
            self.camera.set_exposure(self.exp_spin.value())
            self.camera.set_EMCCD_gain(int(self.gain_spin.value()))
        self._execute_safe_command(update_logic)

    @QtCore.pyqtSlot(np.ndarray)
    def update_plot(self, data):
        # The .T is required for pyqtgraph to display (x, y) correctly from C-order numpy arrays
        self.img.setImage(data.T, autoLevels=self.autolevel_cb.isChecked())

    def closeEvent(self, event):
        self.worker.stop()
        if not isinstance(self.camera, DummyCamera):
            self.camera.setup_shutter(mode="closed")
            self.camera.Close()
        event.accept()

# ARTIQ wrapper
class AndorPreviewFinal(EnvExperiment):
    def build(self):
        try:
            self.camera = AndorEMCCD(
                ExposureTime=0.05,
                gain=0.0,
                hs_speed=0,
                vs_speed=0
            )
        except:
            self.camera = DummyCamera()

    def run(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.gui = AndorCameraGUI(self.camera)
        self.gui.show()
        app.exec()

if __name__ == "__main__":
    from artiq.frontend.artiq_run import main
    sys.argv.append(__file__)
    main()