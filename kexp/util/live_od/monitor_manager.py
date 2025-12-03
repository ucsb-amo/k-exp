from pathlib import Path
import os
import numpy as np

from subprocess import PIPE, run
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread

MONITOR_EXPT_PATH = Path(os.getenv('code')) / 'k-exp' / 'kexp' / \
      'experiments' / 'tools' / 'monitor.py'

class MonitorManager(QThread):
    msg = pyqtSignal(str)
    monitor_stopped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        
    def run(self):
        self.run_expt()

    def run_expt(self):
        try:
            expt_path = MONITOR_EXPT_PATH
            run_expt_command = r"%kpy% & ar " + str(expt_path)
            self.msg.emit("Starting monitor...")
            result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        except Exception as e:
            print(e)