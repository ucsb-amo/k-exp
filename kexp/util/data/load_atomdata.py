import numpy as np
import os
import pickle
import glob
from kexp.analysis.base_analysis import atomdata

data_dir = os.getenv("data")

def load_atomdata(path = []) -> atomdata:
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

