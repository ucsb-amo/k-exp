import numpy as np
import os
import glob
import h5py
from kexp.analysis.atomdata import atomdata
from kexp.config.expt_params import ExptParams
from kexp.util.data.run_info import RunInfo
from kexp.config.camera_params import CameraParams

data_dir = os.getenv("data")

def load_atomdata(idx=0, path = [], unshuffle_xvars=True, crop_type='mot') -> atomdata:
    '''
    Returns the atomdata stored in the `idx`th newest pickle file at `path`.

    Parameters
    ----------
    idx: int
        If a positive value is specified, it is interpreted as a run_id (as
        stored in run_info.run_id), and that data is found and loaded. If zero
        or a negative number are given, data is loaded relative to the most
        recent dataset (idx=0).
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
        if idx <= 0:
            list_of_files.sort(key=lambda x: os.path.getmtime(x))
            list_of_files = np.flip(list_of_files)
            file = list_of_files[-idx]
        if idx > 0:
            run_id = idx
            data_dir_depth_idx = len(data_dir.split('\\')[0:-1]) - 2 # accounts for data directory depth
            rids = [int(file.split("_")[data_dir_depth_idx].split("\\")[-1]) for file in list_of_files]
            rid_idx = rids.index(run_id)
            file = list_of_files[rid_idx]
    else:
        if path.endswith('.hdf5'):
            file = path
        else:
            raise ValueError("The provided path is not a hdf5 file.")
        
    f = h5py.File(file,'r')
    
    params = ExptParams()
    run_info = RunInfo()
    camera_params = CameraParams()
    unpack_group(f,'params',params)
    unpack_group(f,'camera_params',camera_params)
    unpack_group(f,'run_info',run_info)
    images = f['data']['images'][()]
    image_timestamps = f['data']['image_timestamps'][()]
    xvarnames = f.attrs['xvarnames'][()]

    try:
        sort_idx = f['data']['sort_idx'][()]
        sort_N = f['data']['sort_N'][()]
    except:
        sort_idx = []
        sort_N = []

    ad = atomdata(xvarnames,images,image_timestamps,params,camera_params,run_info,
                  sort_idx,sort_N,unshuffle_xvars=unshuffle_xvars,crop_type=crop_type)

    return ad

def unpack_group(file,group_key,obj):
    g = file[group_key]
    keys = list(g.keys())
    for k in keys:
        vars(obj)[k] = g[k][()]