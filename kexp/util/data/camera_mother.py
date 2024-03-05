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

RUN_ID_PATH = r"B:\_K\PotassiumData\run_id.py"
DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")
CHECK_DELAY = 0.25
LOG_UPDATE_INTERVAL = 2.
UPDATE_EVERY = LOG_UPDATE_INTERVAL // CHECK_DELAY

def nothing():
    pass

class CameraMother():
    def __init__(self,start_watching=True):
        self.latest_file = ""
        self.camera_nanny = CameraNanny()
        if start_watching:
            self.watch_for_new_file()
        else:
            pass

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
        name = names.get_first_name()
        print(f"New file found! Run ID {run_id}. Welcome to the world, little {name}...")
        dead = self.birth(file,name)
                
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
    
    def birth(self,data_filepath,name):
       c = CameraBaby(data_filepath,self.camera_nanny,name)
       c.birth()

class CameraBaby(Scribe):
    def __init__(self,data_filepath,camera_nanny:CameraNanny,name,
                 grab_signal_method:nothing):
        super().__init__()

        from kexp.config.expt_params import ExptParams
        from kexp.config.camera_params import CameraParams
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.name = name

        self.camera_nanny = camera_nanny
        self.dataset = []
        self.death = self.dishonorable_death
        self.data_filepath = data_filepath

        self.grab_signal_method = grab_signal_method

        self.img = np.ones((1,1))

    def birth(self):
        try:
            print(f"{self.name}: I am born!")
            self.dataset = self.wait_for_data_available(close=False) # leaves open
            self.read_params() # closes
            self.create_camera() # checks for camera
            print('camera created')
            self.mark_camera_ready() # opens and closes data
            print('camera marked as ready')
            self.dataset = self.check_camera_ready_ack() # opens data
            print('camera ready acknowledged')
            self.grab_loop()
            self.dataset.close()
            self.death()
        except Exception as e:
            print(e)
            self.dataset.close()
            self.death()

    def create_camera(self):
        self.camera = self.camera_nanny.persistent_get_camera(self.camera_params)

    def honorable_death(self):
        print(f"{self.name}: All images captured.")
        print(f"{self.name} has died honorably.")
        return True
    
    def dishonorable_death(self,delete_data=True):
        msg = "Something went wrong. "
        if delete_data:
            msg += "Destroying incomplete data."
            while True:
                try:
                    self.dataset.close()
                    self.wait_for_data_available(check_period=0.25)
                    os.remove(self.data_filepath)
                    break
                except Exception as e:
                    print(e)
        print(msg)
        print(f"{self.name} has died dishonorably.")
        self.update_run_id()
        return True

    def read_params(self):
        unpack_group(self.dataset,'camera_params',self.camera_params)
        unpack_group(self.dataset,'params',self.params)
        self.dataset.close()

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
            self.img, img_timestamp = self.camera.grab()
            self.write_image_to_dataset(count,self.img,img_timestamp)
            self.grab_signal_method()
            count += 1
            print(f"gotem (img {count}/{Nimg})")
            if count >= Nimg:
                self.death = self.honorable_death
                break

    def update_run_id(self):
        pwd = os.getcwd()
        os.chdir(DATA_DIR)
        with open(RUN_ID_PATH,'r+') as f:
            rid = f.read()
            line = f"{rid+1}"
            f.write(line)
        os.chdir(pwd)