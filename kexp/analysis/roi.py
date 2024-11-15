import numpy as np
import pandas as pd
import os
import cv2

import kexp.util.data.server_talk as st
from kexp.analysis.image_processing.compute_ODs import compute_OD

import h5py
from copy import deepcopy

st.check_for_mapped_data_dir()
ROI_CSV_PATH = os.path.join(st.DATA_DIR,"roi.xlsx")

class ROI():
    def __init__(self,
                 run_id=0,
                 roi_id=None,
                 key="",
                 use_saved_roi=True,
                 lite=False):
        self.roix = [-1,-1]
        self.roiy = [-1,-1]
        self.key = key
        self.run_id = run_id
        self.load_roi(roi_id,
                      use_saved=use_saved_roi,
                      lite=lite)

    def crop(self,OD):
        """Crops the given ndarray according to the ROI.

        Args:
            OD (np.ndarray): The ndarray to be cropped.

        Returns:
            ndarray: The cropped ndarray.
        """        
        OD: np.ndarray
        idx_y = range(self.roiy[0],self.roiy[1])
        idx_x = range(self.roix[0],self.roix[1])
        cropOD = OD.take(idx_y,axis=OD.ndim-2).take(idx_x,axis=OD.ndim-1)
        return cropOD

    def load_roi(self,roi_id=None,use_saved=True,lite=False):
        """Loads an ROI according to the provided roi_id.

        Args:
            roi_id (None, int, or str): Specifies which crop to use. If None,
            defaults to the ROI saved in the data if it exists, otherwise
            prompts the user to select an ROI using the GUI. If an int,
            interpreted as an run ID, which will be checked for a saved ROI and
            that ROI will be used. If a string, interprets as a key in the
            roi.xlsx document in the PotassiumData folder.

            use_saved (bool): If False, ignores saved ROI and forces creation of
            a new one.
        """
        
        # Check for ROI saved in the current data file.
        saved_roi_bool = self.read_roi_from_h5(lite=lite)
        if roi_id == None:
            if saved_roi_bool and use_saved:
                print("Using saved ROI.")
            elif saved_roi_bool:
                print("Saved ROI was found, but is being overridden.")
                print("Specify the new ROI.")
                self.select_roi()
            else:
                print("Specify the new ROI.")
                self.select_roi()
        else:
            if saved_roi_bool:
                print("Saved ROI was found, but is being overridden.")

        # Checks for ROI saved in the specified run ID.
        if isinstance(roi_id,int):
            print("ROI specified by Run ID. Attempting to load ROI...")
            saved_roi_bool = self.read_roi_from_h5(roi_id)
            if saved_roi_bool:
                print(f"Using ROI loaded from run {roi_id}.")
            else:
                print(f"Specify the new ROI.")
                self.select_roi()

        if isinstance(roi_id,str):
            print("ROI specified by string. Referencing roi.xslx spreadsheet (PotassiumData)...")
            roi_exists = self.read_roi_from_excel(roi_id)
            if not roi_exists:
                print(f"Creating ROI for key {roi_id}.")
                self.select_roi()
                self._update_excel()

        if self.check_for_blank_roi():
            print("ROI was not specified. Defaulting to whole image.")
            px, py = self.get_image_size()
            self.roix = [0,px]
            self.roiy = [0,py]

    def save_roi_h5(self, lite=False):
        fpath, _ = st.get_data_file(self.run_id,lite=lite)
        with h5py.File(fpath,'r+') as f:
            f.attrs['roix'] = self.roix
            f.attrs['roiy'] = self.roiy

    def save_roi_excel(self,key=""):
        if self.key == "" and key == "":
            raise ValueError("You must specify a key to save the ROI to the spreadsheet.")
        if not isinstance(key,str):
            raise ValueError("The specified key must be a string.")
        
        if not key == "":
            self.key = key
        else:
            # saving will use the key already associated with self.roi.
            pass
        self._update_excel()

    def get_image_size(self):
        """Gets the size in pixels of the images (horizontal, vertical) in this run.

        Returns:
            px, py: The image dimensions (rows, columns).
        """        
        fpath, _ = st.get_data_file(self.run_id)
        with h5py.File(fpath) as f:
            py, px = f['data']['images'].shape[-2:]
        return px, py

    def read_roi_from_h5(self, run_id=[], lite=False):
        """Looks in the hdf5 file with the corresponding run ID and attempts to
        read out a saved ROI. Returns True if successful and False otherwise.

        Args:
            run_id (int): The run ID of the run in which to look for a
            saved ROI.

        Returns:
            bool: Returns True if successful and False otherwise.
        """        
        if run_id == []:
            run_id = self.run_id
        try:
            fpath, run_id = st.get_data_file(run_id,lite=lite)
            with h5py.File(fpath) as f:
                roix = f.attrs['roix']
                roiy = f.attrs['roiy']
            self.roix = roix
            self.roiy = roiy
            print(f"ROI loaded from run {run_id}.")
            return True
        except:
            print(f"No ROI saved in run {run_id}.")
            return False
        
    def read_roi_from_excel(self,key):
        """Reads in the ROI with the corresponding key from the roi spreadsheet
        (roi.xlsx in PotassiumData), if it exists. Returns True if successful
        and False otherwise.

        Args:
            key (str): The key of the ROI to retrieve from the spreadsheet.

        Returns:
            bool: Returns True if successful and False otherwise.
        """        
        self.key = key
        if key == "":
            raise ValueError("ROI key must be a non-empty string.")
        roicsv = pd.read_excel(ROI_CSV_PATH)
        keymatch = roicsv.loc[ roicsv['key'] == self.key ]
        if np.any(keymatch):
            print(f"ROI {key} found.")
            self.key = key
            self.roix = [ keymatch['roix0'].values[0], keymatch['roix1'].values[0] ]
            self.roiy = [ keymatch['roiy0'].values[0], keymatch['roiy1'].values[0] ]
            return True
        else:
            print(f"ROI with key {key} does not exist.")
            return False

    def check_for_blank_roi(self):
        """The ROI selection GUI output is all -1s if no ROI is selected.
        Detects this result so that it can be handled.

        Returns:
            bool: whether or not the ROI selection is valid.
        """        
        return np.all(np.array([*self.roix,*self.roiy]) == -1)
    
    def select_roi(self, run_id=[]):
        """Brings up the GUI to select a new ROI rectangle. The user should
        click and drag (LMB) in order to select a rectangle, then hit Enter to
        submit their selection. RMB clears the rectangle, and Escape/the X
        button will close the window without selecting an ROI (in most cases,
        resulting in an ROI that spans the entire image).

        Args:
            run_id (int, optional): The run_id to use for displaying ODs during
            ROI selection.
        """        
        if run_id == []:
            run_id = self.run_id
        update_bool, roix, roiy = roi_creator(run_id, self.key).get_roi_rectangle()
        if update_bool:
            self.roix, self.roiy = roix, roiy
        else:
            print("ROI not selected, aborting.")

    def _update_excel(self):
        """Saves the ROI to the excel spreadsheet (roi.xlsx) in the
        PotassiumData folder. If the key already exists, updates the existing
        ROI. If not, creates a new line.
        """        
        key = self.key
        if key == "":
            raise ValueError("The key must be nonempty in order to save the ROI.")

        # Read the excel file
        df = pd.read_excel(ROI_CSV_PATH)
        new_values = [*self.roix, *self.roiy]

        # Check if the label exists
        if key in df.iloc[:, 0].values:
            # Find the index of the row with the given label
            index = df[df.iloc[:, 0] == key].index[0]
            # Replace the row values with new values
            df.iloc[index, 1:] = new_values
        else:
            # Append a new row with the given label and new values
            new_row = pd.DataFrame([[key] + new_values], columns=df.columns)
            df = pd.concat([df, new_row], ignore_index=True)

        # Save the updated dataframe back to the excel file
        df.to_excel(ROI_CSV_PATH, index=False)
        print(f"Updated the spreadsheet ROI with key {key}.")

class roi_creator():
    def __init__(self,run_id,key):

        self.key = key
        self.run_id = run_id

        filepath, _ = st.get_data_file(run_id)
        self.h5_file = h5py.File(filepath)
        self.N_img = self.h5_file['data']['images'].shape[0]//3

        self.image = self.get_od(0)

        self.drawing = False
        self.start_x, self.start_y = -1, -1
        self.end_x, self.end_y = -1, -1
        
    def get_od(self,idx):
        """Computes the idx'th OD for display in the ROI selection GUI.

        Args:
            idx (int): the index of the OD to display

        Returns:
            np.ndarray: the OD to display.
        """        
        pwa = self.h5_file['data']['images'][3*idx]
        pwoa = self.h5_file['data']['images'][3*idx+1]
        dark = self.h5_file['data']['images'][3*idx+2]
        od = compute_OD(pwa,pwoa,dark)
        return od
        
    def get_roi_rectangle(self):
        """Brings up the GUI to select an ROI over a display of the ODs from a
        given run.

        Controls:
            LMB + drag: select an ROI rectangle.
            RMB: clear the drawn ROI.
            L/R arrow keys: scroll through ODs from the run.
            Enter: submit your selection.
            Escape / "X" button: close the GUI without submitting selection.

        Returns:
            bool: Whether or not an ROI has been selected.
            tuple: roix, given as [roix0,roix1] (the left and right bounds of
            the ROI).
            tuple: roiy, given as [roiy0,roiy1] (the left and right bounds of
            the ROI).
        """        
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
            # img_index = (img_index + 1) % self.N_img
            # image = self.get_od(img_index)
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
        self.h5_file.close()

        out = np.array([self.start_x, self.start_y, self.end_x, self.end_y])
        update_bool = not np.all(out == -1)
        return update_bool, np.sort([self.start_x, self.end_x]), np.sort([self.end_y, self.start_y])
