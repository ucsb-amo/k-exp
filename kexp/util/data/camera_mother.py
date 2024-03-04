import time
import numpy as np
import os
import h5py
import glob
import names

import pypylon.pylon as py

from kexp.util.data.load_atomdata import unpack_group

from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.camera_nanny import CameraNanny

from kexp.base.sub.scribe import Scribe

import sys

DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")
CHECK_DELAY = 0.25
LOG_UPDATE_INTERVAL = 2.
UPDATE_EVERY = LOG_UPDATE_INTERVAL // CHECK_DELAY

class CameraMother():
    def __init__(self):
        self.latest_file = ""
        self.camera_nanny = CameraNanny()
        self.watch_for_new_file()

    def read_run_id(self):
        with open(RUN_ID_PATH,'r') as f:
            run_id = int(f.read())
        f.close()
        return run_id

    def watch_for_new_file(self):
        new_file_bool = False
        attempts = -1
        print("Mother is watching...")
        while True:
            folderpath=os.path.join(DATA_DIR,'*','*.hdf5')
            list_of_files = glob.glob(folderpath)
            list_of_files.sort(key=lambda x: os.path.getmtime(x))
            latest_file = list_of_files[-1]
            new_file_bool, run_id = self.check_if_file_new(latest_file)
            if new_file_bool:
                self.new_file(latest_file, run_id)
                print("Mother is watching...")
            attempts += 1
            time.sleep(CHECK_DELAY)
            if attempts == UPDATE_EVERY:
                attempts = 0
                print("No new file found.")

    def new_file(self,file,run_id):
        print(f"New file found! Run ID {run_id}. Welcome to the world, little {names.get_first_name()}...")
        dead = self.birth(file)
                
    def check_if_file_new(self,latest_filepath):
        if latest_filepath != self.latest_file:
            data_dir_depth_idx = len(DATA_DIR.split('\\')[0:-1]) - 2
            rid = int(latest_filepath.split("_")[data_dir_depth_idx].split("\\")[-1])
            if rid == self.read_run_id():
                new_file_bool = True
                self.latest_file = latest_filepath
            else:
                new_file_bool = False
        else:
            new_file_bool = False
            rid = None
        return new_file_bool, rid
    
    def birth(self,data_filepath):
       c = CameraBaby(data_filepath,self.camera_nanny)
       dead = c.birth()

class CameraBaby(Scribe):
    def __init__(self,data_filepath,camera_nanny:CameraNanny):
        super().__init__()

        from kexp.config.expt_params import ExptParams
        from kexp.config.camera_params import CameraParams
        self.params = ExptParams()
        self.camera_params = CameraParams()

        self.camera_nanny = camera_nanny
        self.grab_loop = []
        self.dataset = []
        self.death = self.dishonorable_death
        self.data_filepath = data_filepath

    def birth(self):
        print("I am born!")
        self.dataset = self.wait_for_data_available(close=False) # leaves open
        self.read_params() # closes
        self.create_camera() # checks for camera, deletes data if bad
        self.mark_camera_ready() # opens and closes data
        self.dataset = self.check_camera_ready_ack() # opens data
        self.grab_loop()
        self.dataset.close()
        self.death()
    
    def honorable_death(self):
        print("All images captured. Now, death.")
        return True
    
    def dishonorable_death(self,delete_data=True):
        msg = "An error has occurred."
        if delete_data:
            msg += "Destroying incomplete data."
            os.remove(self.data_filepath)
        print(msg)
        return True

    def read_params(self):
        unpack_group(self.dataset,'camera_params',self.camera_params)
        unpack_group(self.dataset,'params',self.params)
        self.dataset.close()

    def create_camera(self):
        self.camera = self.camera_nanny.get_camera(self.camera_params)
        if self.camera == None:
            self.dishonorable_death()

    def write_image_to_dataset(self,idx,img,img_timestamp=0.,
                               close_data_betwixt_shots=False):
        if close_data_betwixt_shots:
            self.wait_for_data_available(close=close_data_betwixt_shots)
        self.dataset['data']['images'][idx] = img
        self.dataset['data']['image_timestamps'][idx] = img_timestamp
        if close_data_betwixt_shots:
            self.dataset.close()

    def grab_loop(self):
        Nimg = int(self.params.N_img)
        count = 0
        while True:
            grab_success, img, img_timestamp = self.camera.grab()
            self.write_image_to_dataset(count,img,img_timestamp)
            count += 1
            if count >= Nimg:
                self.death = self.honorable_death
                break
        if not grab_success:
            self.death = self.dishonorable_death
        
c = CameraMother()