import time
import numpy as np
import os
import h5py
import glob

import pypylon.pylon as py

from kexp.util.data.load_atomdata import unpack_group

from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras 

import sys

DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")
CHECK_DELAY = 0.25
LOG_UPDATE_INTERVAL = 2.
UPDATE_EVERY = LOG_UPDATE_INTERVAL // CHECK_DELAY

class CameraMother():
    def __init__(self):
        self.latest_file = ""
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
        print(f"New file found! Run ID {run_id}. Birthing watcher...")
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
       c = CameraWatcher(data_filepath)
       dead = c.birth()

class CameraWatcher():
    def __init__(self,data_filepath,camera_conn):
        from kexp.config.expt_params import ExptParams
        from kexp.config.camera_params import CameraParams
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.camera_select = ""

        self.camera_conn = camera_conn
        self.grab_loop = []
        self.dataset = []
        self.death = self.dishonorable_death
        self.data_filepath = data_filepath

    def birth(self):
        print("I am born!")
        self.wait_for_data_available(close=False)
        self.read_params()
        self.create_camera()
        time.sleep(self.camera_params.connection_delay)
        self.grab_loop()
        self.death()
    
    def honorable_death(self):
        self.camera.close()
        self.dataset.close()
        print("All images captured. Now, death.")
        return True
    
    def dishonorable_death(self,delete_data=True):
        self.camera.close()
        self.dataset.close()
        msg = "An error has occurred."
        if delete_data:
            msg += "Destroying incomplete data."
            os.remove(self.data_filepath)
        print(msg)
        return True

    def read_params(self,close=False):
        unpack_group(self.dataset,'camera_params',self.camera_params)
        unpack_group(self.dataset,'params',self.params)
        self.camera_select = self.dataset['run_info']['camera_select']
        if close:
            self.dataset.close()

    def wait_for_data_available(self,close=True):
        """Blocks until the file at self.datapath is available. Opens the h5py
        file at self.datapath once available. Unless close=True, leaves the file
        open.
        """        
        import h5py, time
        while True:
            try:
                self.dataset = h5py.File(self.data_filepath,'r+')
                if close:
                    self.dataset.close()
                break
            except Exception as e:
                if "Unable to open file" in str(e):
                    # file is busy -- wait for available
                    time.sleep(0.05)
                else:
                    raise e

    def create_camera(self):
        if self.camera_params.camera_type.decode() == "basler":
            self.camera = BaslerUSB(BaslerSerialNumber=self.camera_params.serial_no,
                                ExposureTime=self.camera_params.exposure_time)
            self.grab_loop = self.start_triggered_grab_basler
        elif self.camera_params.camera_type.decode() == "andor":
            self.camera = AndorEMCCD(ExposureTime=self.camera_params.exposure_time,
                                gain = self.camera_params.em_gain,
                                vs_speed=self.camera_params.vs_speed,
                                vs_amp=self.camera_params.vs_amp)
            self.grab_loop = self.start_triggered_grab_andor
        else:
            print("The camera type in the dataset does not match 'basler' or 'andor'.")
            self.dishonorable_death()

    def write_image_to_dataset(self,idx,img,img_timestamp=0.,
                               close_data_betwixt_shots=False):
        if close_data_betwixt_shots:
            self.wait_for_data_available(close_data_betwixt_shots)
        self.dataset['data']['images'][idx] = img
        self.dataset['data']['image_timestamps'][idx] = img_timestamp
        if close_data_betwixt_shots:
            self.dataset.close()

    def grab_loop(self):
        Nimg = int(self.params.N_img)
        count = 0
        try:


    def start_triggered_grab_basler(self):
        '''
        Start basler camera waiting for triggers, wait for self.params.N_img
        images.
        '''
        Nimg = int(self.params.N_img)
        self.camera.StartGrabbingMax(Nimg, py.GrabStrategy_LatestImages)
        count = 0
        try:
            while self.camera.IsGrabbing():
                grab = self.camera.RetrieveResult(10000, py.TimeoutHandling_ThrowException)
                if grab.GrabSucceeded():
                    print(f'gotem (img {count+1}/{Nimg})')
                    img = np.uint8(grab.GetArray())
                    img_t = grab.TimeStamp
                    self.write_image_to_dataset(count,img,img_t)
                    count += 1
                if count >= Nimg:
                    self.death = self.honorable_death
                    break
        except Exception as e:
            self.death = self.dishonorable_death
            print(e)
        self.camera.StopGrabbing()
        self.camera.Close()
        
    def start_triggered_grab_andor(self):
        """
        Starts the Andor waiting for self.params.N_img triggers. Default 10
        second timeout.
        """
        Nimg = int(self.params.N_img)
        try:
            count = 0
            imgs = self.camera.grab_andor(nframes=Nimg,frame_timeout=10.)
            for img in imgs:
                self.write_image_to_dataset(count,img)
                count += 1
            # for _ in range(Nimg):
            #     img = self.camera.grab_andor(nframes=1,frame_timeout=10.)
            #     self.write_image_to_dataset(count,img)
            #     print(f'gotem (img {count+1}/{Nimg})')
            #     count += 1
            self.death = self.honorable_death
        except Exception as e:
            self.death = self.dishonorable_death
            print("An error occurred with the camera grab. Closing the camera connection.")
            print(e)
            self.camera.Close()
            
c = CameraMother()