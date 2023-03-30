import time
import numpy as np
import os
import pickle

data_dir = os.getenv("data")

class DataSaver():
    def __init__(self):
        pass

    def save_data(self,atomdata):
        '''
        Saves data to a pickle. All attributes which start with "_" are ignored.
        '''
        print("Saving data...")

        fpath = self._data_path(atomdata)

        attrs = list(vars(atomdata))
        keys_to_skip = [p for p in attrs if p.startswith("_")]
        for key in keys_to_skip:
            delattr(atomdata,key)

        with open(fpath, 'wb') as f:
            pickle.dump(atomdata, f)
        print("Done saving parameters!")

    def _data_path(self,atomdata):
        thedate = time.time()
        thedate_local = time.localtime(thedate)
        monthstr = time.strftime("%Y-%m-%d", thedate_local)
        datestring = time.strftime("%Y-%m-%d_%H-%M-%S", thedate_local)
        expt_class = atomdata._expt.__class__.__name__
        filename = "data_" + datestring + "_" + expt_class + ".pickle"
        filepath = os.path.join(data_dir,monthstr,filename)
        return filepath

    