import time
import numpy as np
import os
import pickle
import glob

data_dir = os.getenv("data")

run_id_path = os.path.join(data_dir,"run_id.py")

def load_atomdata(path = []):
    if path == []:
        folderpath=os.path.join(data_dir,'*','*.pickle')
        list_of_files = glob.glob(folderpath)
        file = max(list_of_files, key=os.path.getmtime)
    else:
        if path.endswith('.pickle'):
            file = path
        else:
            raise ValueError("The provided path is not a pickle file.")
        
    with open(file,'rb') as f:
        ad = pickle.load(f)

    return ad

class DataSaver():
    def __init__(self):
        pass

    def save_data(self,atomdata):
        '''
        Saves data to a pickle. All attributes which start with "_" are ignored.
        '''
        print("Saving data...")

        fpath = self._data_path(atomdata)
        atomdata.run_info.filepath = fpath

        attrs = list(vars(atomdata))
        keys_to_skip = [p for p in attrs if p.startswith("_")]
        for key in keys_to_skip:
            delattr(atomdata,key)

        self._update_run_id(atomdata)

        with open(fpath, 'wb') as f:
            pickle.dump(atomdata, f)
            
        print("Done saving parameters!")

    def _data_path(self,atomdata):

        run_id_str = f"{str(atomdata.run_id).zfill(7)}"

        date = atomdata.run_info.run_time
        monthstr = time.strftime("%Y-%m-%d", date)
        datestring = time.strftime("%Y-%m-%d_%H-%M-%S", date)
        
        expt_class = atomdata._expt.__class__.__name__

        filename = run_id_str + "_" + datestring + "_" + expt_class + ".pickle"
        filepath = os.path.join(data_dir,monthstr,filename)
        return filepath

    def _update_run_id(self,atomdata):
        
        line = f"{atomdata.run_id + 1}"
        with open(run_id_path,'w') as f:
            f.write(line)

    def _get_rid(self):
        with open(run_id_path,'r') as f:
            rid = f.read()
        return int(rid)

class DataVault():
    def __init__(self,atomdata_list=[],datalist_path=[]):

        if atomdata_list != []:
            self.atomdata_list = atomdata_list

        self.run_ids = [run_id for ad.run_info.run_id in atomdata_list]
        self.data_filepaths = [fpath for ad.run_info.filepath in atomdata_list]
        self.data_dates = [time.strftime('%Y-%m-%d',date) for ad.run_info.run_datetime in atomdata_list]

