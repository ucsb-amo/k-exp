import numpy as np
import os
import glob
import h5py
from kexp.analysis.atomdata import atomdata
from kexp.config.expt_params import ExptParams
from kexp.util.data.run_info import RunInfo
from kexp.config.camera_params import CameraParams

import kexp.util.data.server_talk as st

from kexp.analysis.roi import ROI

data_dir = os.getenv("data")

def load_atomdata(idx=0, roi_label='', path = "",
                  transpose_idx = [], average_repeats = False) -> atomdata:
    '''
    Returns the atomdata stored in the `idx`th newest file at `path`.

    Parameters
    ----------
    idx: int
        If a positive value is specified, it is interpreted as a run_id (as
        stored in run_info.run_id), and that data is found and loaded. If zero
        or a negative number are given, data is loaded relative to the most
        recent dataset (idx=0).
    roi_label: int or string
        Specifies which crop to use. If left empty, defaults to the ROI saved in
        the data if it exists, otherwise prompts the user to select an ROI using
        the GUI. If an int, interpreted as an run ID, which will be checked for
        a saved ROI and that ROI will be used. If a string, interprets as a key
        in the roi.xlsx document in the PotassiumData folder.
    path: str
        The full path to the file to be loaded. If not specified, loads the file
        as dictated by `idx`.

    Returns
    -------
    ad: atomdata
    '''

    file, rid = st.get_data_file(idx,path)
    
    print(f"run id {rid}")
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
        expt_text = f.attrs['expt_file']
        params_text = f.attrs['params_file']
        cooling_text = f.attrs['cooling_file']
        imaging_text = f.attrs['imaging_file']
    except:
        expt_text = ""
        params_text = ""
        cooling_text = ""
        imaging_text = ""

    try:
        sort_idx = f['data']['sort_idx'][()]
        sort_N = f['data']['sort_N'][()]
    except:
        sort_idx = []
        sort_N = []

    ad = atomdata(xvarnames,images,image_timestamps,params,camera_params,run_info,
                  sort_idx,sort_N,
                  expt_text,params_text,cooling_text,imaging_text,
                  roi_label=roi_label,
                  transpose_idx=transpose_idx, 
                  avg_repeats=average_repeats)
    
    f.close()

    return ad



def unpack_group(file,group_key,obj):
    g = file[group_key]
    keys = list(g.keys())
    for k in keys:
        vars(obj)[k] = g[k][()]