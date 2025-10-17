import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from kexp.analysis.roi import ROI
from kexp.analysis.image_processing import compute_OD, process_ODs
from queue import Queue
from kamo import Potassium39

class Analyzer(QThread):
    analyzed = pyqtSignal()
    def __init__(self, plotting_queue: Queue, viewer=None):
        super().__init__()
        # self.atom = Potassium39()
        
        self.imgs = []
        self.plotting_queue = plotting_queue
        self.roi = []
        self.viewer = viewer

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
        
        # Crop the OD to the current view range for sum calculations
        cropped_od, x_slice, y_slice = self.crop_od_to_view_range(self.od)
        
        # Compute sums from the cropped OD
        cropped_sum_od_x = np.sum(cropped_od, axis=0)  # Sum along y-axis (rows)
        cropped_sum_od_y = np.sum(cropped_od, axis=1)  # Sum along x-axis (columns)
        
        # Use cropped sums instead of the original ones
        self.sum_od_x = cropped_sum_od_x
        self.sum_od_y = cropped_sum_od_y
        
        self.analyzed.emit()
        self.plotting_queue.put((self.img_atoms, self.img_light, self.img_dark, self.od, self.sum_od_x, self.sum_od_y))
        
    def crop_od_to_view_range(self, od):
        """
        Crop the OD array to the current view range of the viewer's OD plot
        
        Args:
            od (numpy.ndarray): The OD array to crop
            
        Returns:
            tuple: (cropped_od, x_slice, y_slice) where slices indicate the cropping ranges
        """
        if self.viewer is None:
            return od, slice(None), slice(None)
        
        try:
            # Get the current view range from the viewer's OD plot
            x_range, y_range = self.viewer.get_od_view_range()
            
            # Convert view coordinates to array indices
            # Clamp to valid array bounds
            x_min = max(0, int(round(x_range[0])))
            x_max = min(od.shape[1], int(round(x_range[1])))
            y_min = max(0, int(round(y_range[0])))
            y_max = min(od.shape[0], int(round(y_range[1])))
            
            # Create slices for cropping
            y_slice = slice(y_min, y_max)
            x_slice = slice(x_min, x_max)
            
            # Crop the OD
            cropped_od = od[y_slice, x_slice]
            
            return cropped_od, x_slice, y_slice
            
        except Exception as e:
            # If anything goes wrong, return the original OD
            print(f"Warning: Could not crop OD to view range: {e}")
            return od, slice(None), slice(None)

    # def compute_atom_number(self,od):
    #     self.atom_cross_section = self.atom.get_cross_section()
    #     dx_pixel = self.camera_params.pixel_size_m / self.camera_params.magnification
        
    #     self.atom_number_fit_area_x = self.fit_area_x * dx_pixel / self.atom_cross_section
    #     self.atom_number_fit_area_y = self.fit_area_y * dx_pixel / self.atom_cross_section

    #     self.atom_number_density = self.od * dx_pixel**2 / self.atom_cross_section
    #     self.atom_number = np.sum(np.sum(self.atom_number_density,-2),-1)