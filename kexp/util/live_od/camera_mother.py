import time
import numpy as np
import os
import h5py
import glob
import names

import pypylon.pylon as py

from kexp.util.data.load_atomdata import unpack_group

from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.util.live_od.camera_nanny import CameraNanny

from kexp.base.sub.scribe import CHECK_PERIOD, Scribe

from PyQt6.QtCore import QThread, pyqtSignal

from queue import Queue

import sys

DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")
CHECK_DELAY = 0.25
LOG_UPDATE_INTERVAL = 2.
UPDATE_EVERY = LOG_UPDATE_INTERVAL // CHECK_DELAY

def nothing():
    pass

class CameraMother(QThread):
    
    new_camera_baby = pyqtSignal(str,str)

    def __init__(self,output_queue:Queue=None,start_watching=True,
                 manage_babies=True,N_runs:int=None,
                 camera_nanny=CameraNanny()):
        super().__init__()

        self.latest_file = ""

        if N_runs == None:
            self.N_runs = - 1
        else:
            self.N_runs = N_runs

        if not output_queue:
            self.output_queue = output_queue
        else:
            self.output_queue = Queue()

        if start_watching:
            self.watch_for_new_file(manage_babies)
        else:
            pass

        self.camera_nanny = camera_nanny

    def run(self):
        self.watch_for_new_file()

    def read_run_id(self):
        with open(RUN_ID_PATH,'r') as f:
            run_id = int(f.read())
        f.close()
        return run_id

    def watch_for_new_file(self,manage_babies=False):
        new_file_bool = False
        attempts = -1
        print("Mother is watching...")
        count = 0
        while True:
            new_file_bool, latest_file, run_id = self.check_files()
            if new_file_bool:
                count += 1
                file, name = self.new_file(latest_file, run_id)
                self.new_camera_baby.emit(file,name)
                self.handle_baby_creation(file, name, manage_babies)
            if count == self.N_runs:
                break
            self.file_checking_timer(attempts)
            
    def file_checking_timer(self,attempts):
        attempts += 1
        time.sleep(CHECK_DELAY)
        if attempts == UPDATE_EVERY:
            attempts = 0
            print("No new file found.")

    def handle_baby_creation(self, file, name, manage_babies):
        if manage_babies:
            self.data_writer = DataHandler(self.output_queue,dataset_path=file)
            self.baby = CameraBaby(file,name,self.output_queue,self.camera_nanny)
            self.baby.image_captured.connect(self.data_writer.start)
            self.baby.run()
            print("Mother is watching...")

    def check_files(self):
        folderpath=os.path.join(DATA_DIR,'*','*.hdf5')
        list_of_files = glob.glob(folderpath)
        list_of_files.sort(key=lambda x: os.path.getmtime(x))
        latest_file = list_of_files[-1]
        new_file_bool, run_id = self.check_if_file_new(latest_file)
        return new_file_bool, latest_file, run_id
    
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

    def new_file(self,file,run_id):
        name = names.get_first_name()
        print(f"New file found! Run ID {run_id}. Welcome to the world, little {name}...")
        return file, name

class DataHandler(QThread,Scribe):
    got_image_from_queue = pyqtSignal(np.ndarray)
    timeout = pyqtSignal()

    def __init__(self,queue:Queue,data_filepath):
        super().__init__()
        self.queue = queue
        self.data_filepath = data_filepath

    def get_img_number(self,N_img):
        self.N_img = N_img

    def run(self):
        self.write_image_to_dataset()

    def write_image_to_dataset(self):
        TIMEOUT = 30
        self.dataset = self.wait_for_data_available(close=False)
        try:
            while True:
                img, img_t, idx = self.queue.get(timeout=TIMEOUT)
                TIMEOUT = 10
                self.got_image_from_queue.emit(img)
                self.dataset['data']['images'][idx] = img
                self.dataset['data']['image_timestamps'][idx] = img_t
                print(f"saved {idx+1}/{self.N_img}")
                if idx == (self.N_img - 1):
                    print('data closed!')
                    self.dataset.close()
                    break
        except Exception as e:
            print(f"No images received after {TIMEOUT} seconds. Did the grab time out?")
            self.dataset.close()
            self.timeout.emit()

class CameraBaby(QThread,Scribe):
    image_captured = pyqtSignal(int)
    camera_grab_start = pyqtSignal(int)
    honorable_death_signal = pyqtSignal()
    dishonorable_death_signal = pyqtSignal()

    def __init__(self,data_filepath,name,output_queue:Queue,
                 camera_nanny:CameraNanny):
        super().__init__()

        from kexp.config.expt_params import ExptParams
        from kexp.config.camera_params import CameraParams
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.name = name

        self.camera_nanny = camera_nanny
        self.queue = output_queue
        self.dataset = []
        self.death = self.dishonorable_death
        self.data_filepath = data_filepath

    def run(self):
        try:
            print(f"{self.name}: I am born!")
            self.dataset = self.wait_for_data_available(close=False) # leaves open
            self.read_params() # closes
            self.create_camera() # checks for camera
            print('camera created')
            self.mark_camera_ready() # opens and closes data
            print('camera marked as ready')
            self.check_camera_ready_ack() # opens data and closes
            print('camera ready acknowledged')
            self.grab_loop()
        except Exception as e:
            print(e)
        self.death()

    def create_camera(self):
        self.camera = self.camera_nanny.persistent_get_camera(self.camera_params)
        # self.camera = vars(self.camera_nanny)[self.camera_params.camera_select]

    def honorable_death(self):
        self.dataset.close()
        print(f"{self.name}: All images captured.")
        print(f"{self.name} has died honorably.")
        self.honorable_death_signal.emit()
        time.sleep(0.1)
        return True
    
    def dishonorable_death(self,delete_data=True):
        self.update_run_id()
        self.remove_incomplete_data(delete_data)
        print(f"{self.name} has died dishonorably.")
        time.sleep(0.1)
        self.dishonorable_death_signal.emit()
        return True

    def read_params(self):
        unpack_group(self.dataset,'camera_params',self.camera_params)
        unpack_group(self.dataset,'params',self.params)
        self.dataset.close()

    def grab_loop(self):
        TIMEOUT = 10.
        Nimg = int(self.params.N_img)
        self.camera_grab_start.emit(Nimg)
        self.camera.start_grab(Nimg,output_queue=self.queue,
                         timeout=TIMEOUT)
        self.death = self.honorable_death

    def update_run_id(self):
        pwd = os.getcwd()
        os.chdir(DATA_DIR)
        with open(RUN_ID_PATH,'r') as f:
            rid = int(f.read())
        with open(RUN_ID_PATH,'w') as f:
            line = f"{rid+1}"
            f.write(line)
        os.chdir(pwd)