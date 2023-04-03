import numpy as np
import os
import _pickle as pickle
import glob
from kexp.analysis.base_analysis import atomdata

data_dir = os.getenv("data")

def load_atomdata(idx=0, path = []) -> atomdata:
    '''
    Returns the atomdata stored in the `idx`th newest pickle file at `path`.

    Parameters
    ----------
    idx: int
        The index of the pickle file to be loaded, relative to the latest file
        (idx=0). (default: idx = 0)
    path: str
        The full path to the file to be loaded. If not specified, loads the file
        as dictated by `idx`.

    Returns
    -------
    ad: atomdata
    '''
    if path == []:
        folderpath=os.path.join(data_dir,'*','*.pickle')
        list_of_files = glob.glob(folderpath)
        list_of_files.sort(key=lambda x: os.path.getmtime(x))
        file = list_of_files[-(idx+1)]
    else:
        if path.endswith('.pickle'):
            file = path
        else:
            raise ValueError("The provided path is not a pickle file.")
        
    with open(file,'rb') as f:
        ad = pickle.load(f)

    return ad

