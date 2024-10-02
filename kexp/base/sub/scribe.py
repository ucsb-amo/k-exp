from kexp.util.data.data_vault import DataSaver
import h5py, time
import numpy as np
import os
from artiq.experiment import TBool, rpc

CHECK_PERIOD = 0.05
WAIT_PERIOD = 0.1
T_NOTIFY = 5
N_NOTIFY = T_NOTIFY // CHECK_PERIOD

DEFAULT_TIMEOUT = 20.

class Scribe():
    def __init__(self):
        self.ds = DataSaver()
        self.data_filepath = ""

    def wait_for_data_available(self,close=True,openmode='r+',
                                check_period=CHECK_PERIOD,
                                timeout=-1.):
        """Blocks until the file at self.datapath is available.
        """
        t0 = time.time()
        count = 0
        while True:
            try:
                f = h5py.File(self.data_filepath,openmode)
                if close:
                    f.close()
                return f
            except Exception as e:
                if "Unable to" in str(e) or "Invalid file name" in str(e) or "cannot access" in str(e):
                    # file is busy -- wait for available
                    # print(e)
                    count += 1
                    time.sleep(check_period)
                    if count == N_NOTIFY:
                        count = 0
                        print("Can't open data. Is another process using it?")
                else:
                    raise e
            if timeout > 0.:
                if time.time() - t0 > timeout:
                    raise ValueError("Timed out waiting for data to be available.")        
                
    def wait_for_camera_ready(self,timeout=-1.) -> TBool:
        count = 1
        t0 = time.time()
        while True:
            if np.mod(count,N_NOTIFY*3) == 0:
                print('Is CameraMother running?')
                count = 1
            elif np.mod(count,N_NOTIFY) == 0:
                print('Waiting for camera ready.') 
            
            if timeout > 0.:
                if time.time() - t0 > timeout:
                    self.dataset.close()
                    self.remove_incomplete_data()
                    raise ValueError("Waiting for camera ready timed out.")

            self.dataset = self.wait_for_data_available(close=False)
            if self.dataset.attrs['camera_ready']:
                self.dataset.attrs['camera_ready_ack'] = 1
                print('Acknowledged camera ready signal.')
                self.dataset.close()
                break
            else:
                self.dataset.close()
                count += 1
            time.sleep(CHECK_PERIOD)
        return True

    def mark_camera_ready(self):
        while True:
            self.dataset = self.wait_for_data_available(close=False,timeout=DEFAULT_TIMEOUT)
            self.dataset.attrs['camera_ready'] = 1
            self.dataset.close()
            break

    def check_camera_ready_ack(self):
        while True:
            self.dataset = self.wait_for_data_available(close=False,timeout=DEFAULT_TIMEOUT)
            if self.dataset.attrs['camera_ready_ack']:
                print('Received ready acknowledgement.')
                self.dataset.close()
                break
            else:
                self.dataset.close()
                time.sleep(WAIT_PERIOD)
        return self.dataset
        
    def write_data(self, expt_filepath, timeout=DEFAULT_TIMEOUT):
        self.dataset = self.wait_for_data_available(close=False,timeout=timeout)
        self.ds.save_data(self, expt_filepath, self.dataset)
        print("Done!")

    def remove_incomplete_data(self,delete_data_bool=True):
        # msg = "Something went wrong."
        if delete_data_bool:
            msg = "Destroying incomplete data."
            while True:
                try:
                    self.dataset.close()
                    self.wait_for_data_available(check_period=0.25,close=True)
                    os.remove(self.data_filepath)
                    break
                except Exception as e:
                    print(e)
            print(msg)