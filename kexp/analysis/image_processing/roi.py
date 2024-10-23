import numpy as np
import pandas as pd
import os
import cv2

from kexp.util.data.server_talk import DATA_DIR, check_for_mapped_data_dir, get_data_file
from kexp.analysis.image_processing.compute_ODs import compute_OD

import h5py
from copy import deepcopy

check_for_mapped_data_dir()
ROI_CSV_PATH = os.path.join(DATA_DIR,"roi.xlsx")

class roi():
    def __init__(self):
        self.roix = []
        self.roiy = []

    def crop(self,OD):
        OD: np.ndarray
        idx_y = range(self.roiy[0],self.roiy[1])
        idx_x = range(self.roix[0],self.roix[1])
        cropOD = OD.take(idx_y,axis=OD.ndim-2).take(idx_x,axis=OD.ndim-1)
        return cropOD

    def read_roi(self):
        roicsv = pd.read_excel(ROI_CSV_PATH)
        keymatch = roicsv.loc[ roicsv['key'] == self.key ]
        if np.any(keymatch):
            self.roix = [ keymatch['roix0'].values[0], keymatch['roix1'].values[0] ]
            self.roiy = [ keymatch['roiy0'].values[0], keymatch['roiy1'].values[0] ]
        else:
            print('ROI not defined.')
            self.select_roi()

    def select_roi(self):
        self._report_msg(0)
        self._save_roi()
        run_id = self.choose_run()
        update_bool, roix, roiy = roi_creator(run_id).get_roi_rectangle()
        if update_bool:
            self.roix, self.roiy = roix, roiy
            self._report_msg(1)
            self.update_excel()
        else:
            print("ROI not selected, aborting")

    def choose_run(self):
        print('Please enter a run ID to use for ROI selection, or press enter to use most recent run.')
        run_id = input('Run ID for ROI selection (or enter to use most recent run).')
        if run_id == '':
            run_id = 0
        run_id = int(run_id)
        return run_id
            
    def _save_roi(self):
        self._roix_revert = deepcopy(self.roix)
        self._roiy_revert = deepcopy(self.roiy)
        
    def revert(self):
        x = deepcopy(self.roix)
        y = deepcopy(self.roiy)
        self.roix = deepcopy(self._roix_revert)
        self.roiy = deepcopy(self._roiy_revert)
        self._roix_revert = x
        self._roiy_revert = y
        self._report_msg(2)

    def _report_msg(self,msg_idx):
        if msg_idx == 0:
            print(f"Current ROI for {self.key}:\n"+
                  f"roix = [{self.roix[0]}, {self.roix[1]}]\n"+
                  f"roiy = [{self.roiy[0]}, {self.roiy[1]}]\n")
        elif msg_idx == 1:
            print(f"New ROI saved for {self.key}:\n"+
                  f"roix = [{self.roix[0]}, {self.roix[1]}]\n"+
                  f"roiy = [{self.roiy[0]}, {self.roiy[1]}]\n")
            print(f"Revert changes with roi.revert()")
        elif msg_idx == 2:
            print(f"ROI reverted for {self.key}:\n"+
                  f"roix = [{self.roix[0]}, {self.roix[1]}]\n"+
                  f"roiy = [{self.roiy[0]}, {self.roiy[1]}]\n")
            print(f"Revert changes with roi.revert()")

    def update_excel(self):
        # Read the excel file
        df = pd.read_excel(ROI_CSV_PATH)
        new_values = [*self.roix, *self.roiy]

        # Check if the label exists
        if self.key in df.iloc[:, 0].values:
            # Find the index of the row with the given label
            index = df[df.iloc[:, 0] == self.key].index[0]
            # Replace the row values with new values
            df.iloc[index, 1:] = new_values
        else:
            # Append a new row with the given label and new values
            new_row = pd.DataFrame([[self.key] + new_values], columns=df.columns)
            df = pd.concat([df, new_row], ignore_index=True)

        # Save the updated dataframe back to the excel file
        df.to_excel(ROI_CSV_PATH, index=False)

class roi_creator():
    def __init__(self,run_id):

        filepath, _ = get_data_file(run_id)
        self.h5_file = h5py.File(filepath)
        self.N_img = self.h5_file['data']['images'].shape[0]//3

        self.image = self.get_od(0)

        self.drawing = False
        self.start_x, self.start_y = -1, -1
        self.end_x, self.end_y = -1, -1
        
    def get_od(self,idx):
        pwa = self.h5_file['data']['images'][3*idx]
        pwoa = self.h5_file['data']['images'][3*idx+1]
        dark = self.h5_file['data']['images'][3*idx+2]
        od = compute_OD(pwa,pwoa,dark)
        return od
        
    def get_roi_rectangle(self):

        image = self.image
        img_index = 0

        def draw_rectangle(event, x, y, flags, param):
            
            if event == cv2.EVENT_LBUTTONDOWN:
                self.drawing = True
                self.start_x, self.start_y = x, y
                
            elif event == cv2.EVENT_MOUSEMOVE:
                if self.drawing:
                    self.end_x = max(min(x, image.shape[1] - 1), 0)
                    self.end_y = max(min(y, image.shape[0] - 1), 0)
                    
            elif event == cv2.EVENT_LBUTTONUP:
                self.drawing = False
                self.end_x = max(min(x, image.shape[1] - 1), 0)
                self.end_y = max(min(y, image.shape[0] - 1), 0)

            elif event == cv2.EVENT_RBUTTONDOWN:
                self.drawing = False
                self.start_x = -1
                self.start_y = -1
                self.end_x = -1
                self.end_y = -1

        cv2.namedWindow('OD')
        cv2.setMouseCallback('OD', draw_rectangle)

        while True:
            img_copy = image.copy()
            if self.start_x != -1 and self.start_y != -1 and self.end_x != -1 and self.end_y != -1:
                cv2.rectangle(img_copy, (self.start_x, self.start_y), (self.end_x, self.end_y), (255, 255, 255), 2)
            cv2.imshow('OD', img_copy)
            
            key = cv2.waitKeyEx(1)
            if key == 13:  # Enter key
                break
            elif key == 2555904:  # Right arrow key ➡️
                img_index = (img_index + 1) % self.N_img
                image = self.get_od(img_index)
            elif key == 2424832:  # Left arrow key ⬅️
                img_index = (img_index - 1) % self.N_img
                image = self.get_od(img_index)
            if cv2.getWindowProperty('OD',cv2.WND_PROP_VISIBLE) < 1: # if window x button clicked
                break
            if key == 27: # escape key
                break

        cv2.destroyAllWindows()

        out = np.array([self.start_x, self.start_y, self.end_x, self.end_y])
        update_bool = not np.all(out == -1)
        return update_bool, [self.start_x, self.start_y], [self.end_x, self.end_y]
