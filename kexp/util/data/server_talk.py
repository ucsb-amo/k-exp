import os
import subprocess
from datetime import datetime, timedelta
import glob
import numpy as np
import random
import winsound

DATA_DIR = os.getenv("data")
DATA_DIR_FILE_DEPTH_IDX = len(DATA_DIR.split('\\')[0:-1]) - 2
MAP_BAT_PATH = "\"G:\\Shared drives\\Weld Lab Shared Drive\\Infrastructure\\map_network_drives_PeterRecommended.bat\""
FIRST_DATA_FOLDER_DATE = datetime(2023,6,22)
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")
SOUNDS_DIR = os.path.join(DATA_DIR,'done_sounds')

def set_data_dir(lite=False):
    global DATA_DIR
    global DATA_DIR_FILE_DEPTH_IDX

    DATA_DIR = os.getenv("data")
    DATA_DIR_FILE_DEPTH_IDX = len(DATA_DIR.split('\\')[0:-1]) - 2

    if lite:
        DATA_DIR = os.path.join(DATA_DIR,"_lite")
        DATA_DIR_FILE_DEPTH_IDX += 1

def get_data_file(idx=0, path="", lite=False):
    '''
    Returns the data file path corresponding to index idx. For idx > 0, idx is
    intepreted as a run ID. For idx = 0, gets the latest data file path. For idx
    < 0, increments chronologically backward from the latest file.

    If path is instead specified, loads the file at the specified path.

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
    str: the full path to the specified data file
    int: the run ID for the specified data file
    '''
    if path == "":
        latest_file = get_latest_data_file(lite)
        latest_rid = run_id_from_filepath(latest_file,lite)
        if idx == 0:
            file = latest_file
        if idx <= 0:
            file = recurse_find_data_file(latest_rid+idx,lite)
        if idx > 0:
            if latest_rid - idx < 10000:
                file = recurse_find_data_file(idx,lite)
            else:
                file = all_glob_find_data_file(idx,lite)
    else:
        if path.endswith('.hdf5'):
            file = path
        else:
            raise ValueError("The provided path is not a hdf5 file.")
        
    rid = run_id_from_filepath(file,lite)
    return file, rid

def check_for_mapped_data_dir():
    set_data_dir()
    if not os.path.exists(DATA_DIR):
        print(f"Data dir ({DATA_DIR}) not found. Attempting to re-map network drives.")
        cmd = MAP_BAT_PATH         
        result = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        if not os.path.exists(DATA_DIR):
            raise ValueError(f"Data dir still not found. Are you connected to the physics network?") 
        else:
            print("Network drives successfully mapped.")

def get_latest_date_folder(lite=False,days_ago=0):
    set_data_dir(lite)
    date = datetime.today() - timedelta(days=days_ago)
    date_str = date.strftime('%Y-%m-%d')
    folderpath=os.path.join(DATA_DIR,date_str)
    if not os.path.exists(folderpath) or not os.listdir(folderpath):
        folderpath = get_latest_date_folder(lite,days_ago+1)
    return folderpath
    
def get_latest_data_file(lite=False):
    check_for_mapped_data_dir()
    folderpath = get_latest_date_folder(lite)
    pattern = os.path.join(folderpath,'*.hdf5')
    files = list(glob.iglob(pattern))
    # Filter out files that do not exist before sorting
    existing_files = [f for f in files if os.path.exists(f)]
    files_sorted = sorted(
        existing_files,
        key=os.path.getmtime,
        reverse=True)
    latest_file = None
    for file in files_sorted:
        try:
            # Try to access getmtime, which will raise FileNotFoundError if missing
            os.path.getmtime(file)
            latest_file = file
            break
        except FileNotFoundError:
            continue
    return latest_file

def recurse_find_data_file(r_id,lite=False,days_ago=0):
    date = datetime.today() - timedelta(days=days_ago)

    if date < FIRST_DATA_FOLDER_DATE:
        raise ValueError(f"Data file with run ID {r_id:1.0f} was not found.")
    
    date_str = date.strftime('%Y-%m-%d')

    set_data_dir(lite)
    folderpath=os.path.join(DATA_DIR,date_str)

    if os.path.exists(folderpath):
        pattern = os.path.join(folderpath,'*.hdf5')
        files = np.array(list(glob.iglob(pattern)))
        r_ids = np.array([run_id_from_filepath(file,lite) for file in files])

        files_mask = (r_id == r_ids)
        file_with_rid = files[files_mask]

        if len(file_with_rid) > 1:
            print(f"There are two data files with run ID {r_id:1.0f}. Choosing the more recent one.")
            file_with_rid = max(file_with_rid,key=os.path.getmtime)
        elif len(file_with_rid) == 1:
            file_with_rid = file_with_rid[0]
        
        if not file_with_rid:
            file_with_rid = recurse_find_data_file(r_id,lite,days_ago+1)
    else:
        file_with_rid = recurse_find_data_file(r_id,lite,days_ago+1)
    return file_with_rid

def all_glob_find_data_file(run_id,lite=False):
    set_data_dir(lite)
    folderpath=os.path.join(DATA_DIR,'*','*.hdf5')
    list_of_files = glob.glob(folderpath)
    rids = [run_id_from_filepath(file,lite) for file in list_of_files]
    rid_idx = rids.index(run_id)
    file = list_of_files[rid_idx]
    return file

def run_id_from_filepath(filepath,lite=False):
    set_data_dir(lite)
    run_id = int(filepath.split("_")[DATA_DIR_FILE_DEPTH_IDX].split("\\")[-1])
    return run_id

def get_run_id():
    set_data_dir()

    pwd = os.getcwd()
    os.chdir(DATA_DIR)
    with open(RUN_ID_PATH,'r') as f:
        rid = f.read()
    os.chdir(pwd)
    return int(rid)

def update_run_id(run_info):
    set_data_dir()

    pwd = os.getcwd()
    os.chdir(DATA_DIR)

    line = f"{run_info.run_id + 1}"
    with open(RUN_ID_PATH,'w') as f:
        f.write(line)

    os.chdir(pwd)

def play_random_sound():
    set_data_dir()
    files = [f for f in os.listdir(SOUNDS_DIR) if os.path.isfile(os.path.join(SOUNDS_DIR, f))]
    file = random.choice(files)
    winsound.PlaySound(os.path.join(SOUNDS_DIR,file), winsound.SND_FILENAME)

def create_lite_copy(run_idx,roi_id=None,use_saved_roi=True):
    from kexp.util.data import RunInfo, DataSaver
    from kexp.analysis.atomdata import unpack_group
    import h5py
    from kexp.analysis import ROI

    original_data_filepath, rid = get_data_file(run_idx)

    ri = RunInfo()
    with h5py.File(original_data_filepath) as file:
        unpack_group(file,'run_info',ri)

    ds = DataSaver()
    lite_data_path, lite_data_folder = ds._data_path(ri,lite=True)

    if not os.path.exists(lite_data_folder):
        os.mkdir(lite_data_folder)

    with h5py.File(lite_data_path,'w') as f_lite:
        with h5py.File(original_data_filepath,'r') as f_src:
            # copy over other datasets (not data)
            keys = f_src.keys()
            for key in keys:
                if key != 'data':
                    f_src.copy(f_src[key],f_lite,key)

            # copy over non-image data
            dkeys = f_src['data'].keys()
            f_lite.create_group('data')
            for key in dkeys:
                if key != 'images':
                    f_src.copy(f_src['data'][key],f_lite['data'],key)

            # copy over attributes
            akeys = f_src.attrs.keys()
            for key in akeys:
                f_lite.attrs[key] = f_src.attrs[key]

            roi = ROI(rid,roi_id=roi_id,use_saved_roi=use_saved_roi)
            
            N_img = f_src['data']['images'].shape[0]
            px = np.diff(roi.roix)[0]
            py = np.diff(roi.roiy)[0]

            f_lite.attrs['roix'] = [0,px]
            f_lite.attrs['roiy'] = [0,py]

            dtype = f_src['data']['images'][0].dtype
            images = np.zeros((N_img,py,px),dtype=dtype)

            for idx in range(N_img):
                images[idx] = roi.crop(f_src['data']['images'][idx])
            f_lite['data']['images'] = images
    print(f'Lite version of run {rid} saved at {lite_data_path}.')