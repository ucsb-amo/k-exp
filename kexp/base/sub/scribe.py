from kexp.util.data import DataSaver
import h5py, time
import numpy as np

CHECK_PERIOD = 0.05
WAIT_PERIOD = 0.1
T_NOTIFY = 3
N_NOTIFY = T_NOTIFY // CHECK_PERIOD

class Scribe():
    def __init__(self):
        self.ds = DataSaver()
        self.data_filepath = ""

    def wait_for_data_available(self,close=True,openmode='r+'):
        """Blocks until the file at self.datapath is available.
        """       
        t0 = time.time()
        while True:
            try:
                f = h5py.File(self.data_filepath,openmode)
                if close:
                    f.close()
                return f
            except Exception as e:
                if "Unable to open file" in str(e):
                    # file is busy -- wait for available
                    time.sleep(CHECK_PERIOD)
                else:
                    raise e
                
    def wait_for_camera_ready(self):
        count = 0
        while True:
            if np.mod(count,N_NOTIFY*3) == 0:
                print('Is CameraMother running?')
                count = 1
            elif np.mod(count,N_NOTIFY) == 0:
                print('Waiting for camera ready.') 

            data_obj = self.wait_for_data_available(close=False)
            if data_obj.attrs['camera_ready']:
                data_obj.attrs['camera_ready_ack'] = 1
                break
            else:
                data_obj.close()
                count += 1
            time.sleep(CHECK_PERIOD)

    def mark_camera_ready(self):
        while True:
            data_obj = self.wait_for_data_available()
            data_obj.attrs['camera_ready'] = 1
            data_obj.close()
            break

    def check_camera_ready_ack(self):
        while True:
            data_obj = self.wait_for_data_available(close=False)
            if data_obj.attrs['camera_ready_ack']:
                break
            else:
                data_obj.close()
                time.sleep(WAIT_PERIOD)
        return data_obj
        
    def write_data(self, expt_filepath):
        self.wait_for_data_available()
        self.ds.save_data(self, expt_filepath)
        print("Done!")