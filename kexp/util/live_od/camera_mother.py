import time
import numpy as np
import os
import h5py
import names

import pypylon.pylon as py

from kexp.analysis.atomdata import unpack_group

from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.util.live_od.camera_nanny import CameraNanny
from kexp.util.data.server_talk import get_latest_data_file, run_id_from_filepath
from kexp.util.increment_run_id import update_run_id

from kexp.base.sub.scribe import Scribe
from kexp.config.timeouts import (CAMERA_MOTHER_CHECK_DELAY as CHECK_DELAY,
                                   UPDATE_EVERY, DATA_SAVER_TIMEOUT)

from PyQt6.QtCore import QThread, pyqtSignal

from queue import Queue, Empty

DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")

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
        return run_id

    def watch_for_new_file(self,manage_babies=False):
        new_file_bool = False
        attempts = -1
        print("\nMother is watching...\n")
        count = 0
        while True:
            new_file_bool, latest_file, run_id = self.check_files()
            if new_file_bool:
                count += 1
                file, name = self.new_file(latest_file, run_id)
                self.new_camera_baby.emit(file, name)
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
            self.data_writer = DataHandler(self.output_queue,data_filepath=file)
            self.baby = CameraBaby(file,name,self.output_queue,self.camera_nanny)
            self.baby.image_captured.connect(self.data_writer.start)
            self.baby.run()
            print("Mother is watching...")

    def check_files(self):
        latest_file = get_latest_data_file()
        new_file_bool, run_id = self.check_if_file_new(latest_file)
        return new_file_bool, latest_file, run_id
    
    def check_if_file_new(self,latest_filepath):
        if latest_filepath != self.latest_file:
            rid = run_id_from_filepath(latest_filepath)
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
    save_data_bool_signal = pyqtSignal(int)
    image_type_signal = pyqtSignal(bool)

    def __init__(self,queue:Queue,data_filepath):
        self.data_filepath = data_filepath
        super().__init__()
        self.queue = queue

        from kexp.config.expt_params import ExptParams
        from kexp.config.camera_id import CameraParams
        from kexp.util.data.run_info import RunInfo
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()
        self.interrupted = False

    def get_save_data_bool(self,save_data_bool):
        self.save_data = save_data_bool

    def get_img_number(self,N_img,N_shots,N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot

    def run(self):
        if self.interrupted:
            self.quit()
        self.write_image_to_dataset()

    def read_params(self):
        with self.wait_for_data_available() as f:
            unpack_group(f,'camera_params',self.camera_params)
            unpack_group(f,'params',self.params)
            unpack_group(f,'run_info',self.run_info)
        self.image_type_signal.emit(self.run_info.imaging_type)
        self.save_data_bool_signal.emit(self.run_info.save_data)

    def write_image_to_dataset(self):
        try:
            if self.save_data:
                f = self.wait_for_data_available(timeout=DATA_SAVER_TIMEOUT,
                                                 check_interrupt_method=self.break_check)
            while True:
                if self.interrupted:
                    break
                try:
                    img, _, idx = self.queue.get(block=False)
                    img_t = time.time()
                    self.got_image_from_queue.emit(img)
                    if self.save_data:
                        f['data']['images'][idx] = img
                        f['data']['image_timestamps'][idx] = img_t
                        print(f"saved {idx+1}/{self.N_img}")
                    if idx == (self.N_img - 1):
                        break
                except:
                    self.msleep(1)
        except Exception as e:
            # print(f"No images received after {TIMEOUT} seconds. Did the grab time out?")
            print(e)
        try:
            if self.save_data: f.close()
        except:
            pass

    def break_check(self):
        return self.interrupted

class CameraBaby(QThread):
    image_captured = pyqtSignal(int)
    camera_connect = pyqtSignal(str)
    camera_grab_start = pyqtSignal(int,int,int)
    save_data_bool_signal = pyqtSignal(int)
    image_type_signal = pyqtSignal(bool)
    honorable_death_signal = pyqtSignal()
    dishonorable_death_signal = pyqtSignal()
    done_signal = pyqtSignal()
    break_signal = pyqtSignal()
    cam_status_signal = pyqtSignal(int)

    def __init__(self,data_handler:DataHandler,
                 name,output_queue:Queue,
                 camera_nanny:CameraNanny):
        super().__init__()

        self.name = name
        self.camera_nanny = camera_nanny
        self.camera = DummyCamera()
        self.queue = output_queue
        self.death = self.dishonorable_death
        self.data_handler = data_handler
        self.interrupted = False
        self.dead = False

    def run(self):
        try:
            self.cam_status_signal.emit(0)
            print(f"{self.name}: I am born!")
            self.data_handler.read_params()
            self.handshake()
            self.grab_loop()
        except Exception as e:
            print(e)
        if self.interrupted:
            print('Grab loop interrupted, shutting down.')
        self.death()
        if self.interrupted:
            self.dead = True
        self.done_signal.emit()

    def handshake(self):
        self.create_camera() # checks for camera
        self.cam_status_signal.emit(1)
        if self.camera.is_opened():
            self.data_handler.mark_camera_ready(self.break_check)
        else:
            raise ValueError("Camera not ready")
        self.cam_status_signal.emit(2)
        self.data_handler.check_camera_ready_ack(self.break_check)
        self.cam_status_signal.emit(3)

    def create_camera(self):
        self.camera = self.camera_nanny.persistent_get_camera(self.data_handler.camera_params)
        self.camera_nanny.update_params(self.camera,self.data_handler.camera_params)
        camera_select = self.data_handler.camera_params.key
        if type(camera_select) == bytes: 
            camera_select = camera_select.decode()
        self.camera_connect.emit(camera_select)

    def honorable_death(self):
        try:
            self.camera.stop_grab()
        except:
            pass
        print(f"{self.name}: All images captured.")
        print(f"{self.name} has died honorably.")
        time.sleep(0.1)
        self.honorable_death_signal.emit()
        self.cam_status_signal.emit(-1)
        return True
    
    def dishonorable_death(self,delete_data=True):
        try:
            self.camera.stop_grab()
        except:
            pass
        self.data_handler.remove_incomplete_data(delete_data)
        print(f"{self.name} has died dishonorably.")
        time.sleep(0.1)
        self.dishonorable_death_signal.emit()
        self.cam_status_signal.emit(-1)
        return True

    def grab_loop(self):
        N_img = int(self.data_handler.params.N_img)
        N_shots = int(self.data_handler.params.N_shots)
        N_pwa_per_shot = int(self.data_handler.params.N_pwa_per_shot)
        self.camera_grab_start.emit(N_img,N_shots,N_pwa_per_shot)
        self.camera.start_grab(N_img,output_queue=self.queue,
                    check_interrupt_method=self.break_check)
        if not self.interrupted:
            self.death = self.honorable_death

    def break_check(self):
        return self.interrupted