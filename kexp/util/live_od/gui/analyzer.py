import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from kexp.analysis.roi import ROI
from kexp.analysis.image_processing import compute_OD, process_ODs
from queue import Queue

class Analyzer(QThread):
    analyzed = pyqtSignal()
    def __init__(self, plotting_queue: Queue):
        super().__init__()
        self.imgs = []
        self.plotting_queue = plotting_queue
        self.roi = []
    def get_img_number(self, N_img, N_shots, N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot
    def get_analysis_type(self, imaging_type):
        self.imaging_type = imaging_type
    def got_img(self, img):
        self.imgs.append(np.asarray(img))
        if len(self.imgs) == (self.N_pwa_per_shot + 2):
            self.analyze()
            self.imgs = []
    def analyze(self):
        self.img_atoms = self.imgs[0]
        self.img_light = self.imgs[self.N_pwa_per_shot]
        self.img_dark = self.imgs[self.N_pwa_per_shot + 1]
        self.od_raw = compute_OD(self.img_atoms, self.img_light, self.img_dark, imaging_type=self.imaging_type)
        self.od_raw = np.array([self.od_raw])
        self.od, self.sum_od_x, self.sum_od_y = process_ODs(self.od_raw, self.roi)
        self.od_raw = self.od_raw[0]
        self.od = self.od[0]
        self.sum_od_x = self.sum_od_x[0]
        self.sum_od_y = self.sum_od_y[0]
        self.analyzed.emit()
        self.plotting_queue.put((self.img_atoms, self.img_light, self.img_dark, self.od, self.sum_od_x, self.sum_od_y))
