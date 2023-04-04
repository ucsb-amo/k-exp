import numpy as np
import os
import _pickle as pickle
import glob
import h5py
from kexp.analysis.base_analysis import atomdata
from kexp.config.expt_params import ExptParams
from kexp.util.data.run_info import RunInfo

data_dir = os.getenv("data")

# def load_atomdata(idx=0, path = []) -> atomdata:
#     '''
#     Returns the atomdata stored in the `idx`th newest pickle file at `path`.

#     Parameters
#     ----------
#     idx: int
#         The index of the pickle file to be loaded, relative to the latest file
#         (idx=0). (default: idx = 0)
#     path: str
#         The full path to the file to be loaded. If not specified, loads the file
#         as dictated by `idx`.

#     Returns
#     -------
#     ad: atomdata
#     '''
#     if path == []:
#         folderpath=os.path.join(data_dir,'*','*.pickle')
#         list_of_files = glob.glob(folderpath)
#         list_of_files.sort(key=lambda x: os.path.getmtime(x))
#         file = list_of_files[-(idx+1)]
#     else:
#         if path.endswith('.pickle'):
#             file = path
#         else:
#             raise ValueError("The provided path is not a pickle file.")
        
#     with open(file,'rb') as f:
#         ad = pickle.load(f)

#     return ad

def load_atomdata(idx=0,path = [],crop_type='mot') -> atomdata:
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
        folderpath=os.path.join(data_dir,'*','*.hdf5')
        list_of_files = glob.glob(folderpath)
        list_of_files.sort(key=lambda x: os.path.getmtime(x))
        file = list_of_files[-(idx+1)]
    else:
        if path.endswith('.hdf5'):
            file = path
        else:
            raise ValueError("The provided path is not a hdf5 file.")
        
    f = h5py.File(file,'r')
    
    params = ExptParams()
    run_info = RunInfo()

    unpack_group(f,'params',params)
    unpack_group(f,'run_info',run_info)
    images = f['data']['images'][()]
    image_timestamps = f['data']['image_timestamps'][()]
    xvarnames = f.attrs['xvarnames'][()]

    ad = atomdata(xvarnames,images,image_timestamps,params,run_info,crop_type=crop_type)

    return ad

def unpack_group(file,group_key,obj):
    g = file[group_key]
    keys = list(g.keys())
    for k in keys:
        vars(obj)[k] = g[k][()]
