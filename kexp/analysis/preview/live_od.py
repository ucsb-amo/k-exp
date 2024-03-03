import numpy as np
import sys
from subprocess import PIPE, run
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

from kexp.util.data.camera_mother import CameraMother

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.camera_mother = CameraMother()
        

