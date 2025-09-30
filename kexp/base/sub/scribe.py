from kexp.util.data.data_vault import DataSaver
import h5py, time
import numpy as np
import os
from artiq.experiment import TBool, rpc
from kexp.config.timeouts import (DEFAULT_TIMEOUT, N_NOTIFY,
                                   CHECK_CAMERA_READY_ACK_PERIOD, REMOVE_DATA_POLL_INTERVAL,
                                   CHECK_FOR_DATA_AVAILABLE_PERIOD as CHECK_PERIOD)

def nothing():
    pass

class Scribe():
    def __init__(self, data_filepath=""):
        self.ds = DataSaver()
        if data_filepath != "":
            self.data_filepath = data_filepath

    def wait_for_data_available(self,openmode='r+',
                                check_period=CHECK_PERIOD,
                                timeout=DEFAULT_TIMEOUT,
                                check_interrupt_method=nothing):
        """Blocks until the file at self.datapath is available.
        """
        close = False
        t0 = time.time()
        count = 0
        while True:
            try:
                if check_interrupt_method():
                    break
                f = h5py.File(self.data_filepath,openmode)
                return f
            except Exception as e:
                if "Unable to" in str(e) or "Invalid file name" in str(e) or "cannot access" in str(e):
                    # file is busy -- wait for available
                    count += 1
                    time.sleep(check_period)
                    if count == N_NOTIFY:
                        count = 0
                        print("Can't open data. Is another process using it?")
                else:
                    raise e
            self._check_data_file_exists()
            if timeout > 0.:
                if time.time() - t0 > timeout:
                    raise ValueError("Timed out waiting for data to be available.")        
                
    def wait_for_camera_ready(self,timeout=-1.) -> TBool:
        count = 1
        t0 = time.time()
        waiting = True
        while waiting:
            try:
                self._check_data_file_exists()
            except:
                break
            if np.mod(count,N_NOTIFY) == 0:
                print('Waiting for camera ready.') 
                print(self.run_info.run_id)
            
            if timeout > 0.:
                if time.time() - t0 > timeout:
                    self.remove_incomplete_data()
                    raise ValueError("Waiting for camera ready timed out.")

            with self.wait_for_data_available() as f:
                if f.attrs['camera_ready']:
                    f.attrs['camera_ready_ack'] = 1
                    print('Acknowledged camera ready signal.')
                    waiting = False
                else:
                    count += 1
            time.sleep(CHECK_PERIOD)
        return True

    def mark_camera_ready(self,check_interrupt_method=nothing):
        with self.wait_for_data_available(check_interrupt_method=check_interrupt_method) as f:
            f.attrs['camera_ready'] = 1

    def check_camera_ready_ack(self,check_interrupt_method=nothing):
        while True:
            with self.wait_for_data_available(check_interrupt_method=check_interrupt_method) as f:
                if f.attrs['camera_ready_ack']:
                    print('Received ready acknowledgement.')
                    break
                else:
                    time.sleep(CHECK_CAMERA_READY_ACK_PERIOD)
        
    def write_data(self, expt_filepath):
        with self.wait_for_data_available() as f:
            self.ds.save_data(self, expt_filepath, f)
            print("Done!")

    def remove_incomplete_data(self,delete_data_bool=True):
        # msg = "Something went wrong."
        if delete_data_bool:
            msg = "Destroying incomplete data."
            count = 0
            while True:
                try:
                    with self.wait_for_data_available(check_period=REMOVE_DATA_POLL_INTERVAL) as f:
                        pass
                    os.remove(self.data_filepath)
                    print(msg)
                except Exception as e:
                    if "Unable to" in str(e) or "Invalid file name" in str(e) or "cannot access" in str(e):
                        # file is busy -- wait for available
                        count += 1
                        time.sleep(CHECK_PERIOD)
                        if count == N_NOTIFY:
                            count = 0
                            print("Can't open data. Is another process using it?")
                    else:
                        raise e
                if not self._check_data_file_exists(raise_error=False):
                    break

    def _check_data_file_exists(self, raise_error=True) -> TBool:
        """
        Checks if the data file exists if saving data is enabled. Raises an
        error if not found.
        """
        if hasattr(self, 'run_info'):
            filepath = getattr(self.run_info, 'filepath', None)
            if isinstance(filepath, list):
                # If filepath is a list, check all paths
                paths = filepath
            else:
                paths = [filepath]
            for path in paths:
                if path and not os.path.exists(path):
                    if raise_error:
                        raise RuntimeError(f"Data file for run ID {self.run_info.run_id} not found.")
                    else:
                        return False
            return True