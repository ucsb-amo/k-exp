import os
import subprocess
from datetime import datetime, timedelta
import glob
import numpy as np

DATA_DIR = os.getenv("data")
DATA_DIR_FILE_DEPTH_IDX = len(DATA_DIR.split('\\')[0:-1]) - 2
MAP_BAT_PATH = "\"G:\\Shared drives\\Weld Lab Shared Drive\\Infrastructure\\map_network_drives_PeterRecommended.bat\""
FIRST_DATA_FOLDER_DATE = datetime(2023,6,22)
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")

def check_for_mapped_data_dir(data_dir=DATA_DIR):
    if not os.path.exists(data_dir):
        print(f"Data dir ({data_dir}) not found. Attempting to re-map network drives.")
        cmd = MAP_BAT_PATH         
        result = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        if not os.path.exists(data_dir):
            raise ValueError(f"Data dir still not found. Are you connected to the physics network?") 
        else:
            print("Network drives successfully mapped.")

def get_latest_date_folder(days_ago=0):
    date = datetime.today() - timedelta(days=days_ago)
    date_str = date.strftime('%Y-%m-%d')
    folderpath=os.path.join(DATA_DIR,date_str)
    if not os.path.exists(folderpath):
        folderpath = get_latest_date_folder(days_ago+1)
    return folderpath
    
def get_latest_data_file():
    check_for_mapped_data_dir()
    folderpath = get_latest_date_folder(0)
    pattern = os.path.join(folderpath,'*.hdf5')
    latest_file = max(glob.iglob(pattern),key=os.path.getmtime)
    return latest_file

def recurse_find_data_file(r_id,days_ago=0):
    date = datetime.today() - timedelta(days=days_ago)

    if date < FIRST_DATA_FOLDER_DATE:
        raise ValueError(f"Data file with run ID {r_id:1.0f} was not found.")
    
    date_str = date.strftime('%Y-%m-%d')
    folderpath=os.path.join(DATA_DIR,date_str)

    if os.path.exists(folderpath):
        pattern = os.path.join(folderpath,'*.hdf5')
        files = np.array(list(glob.iglob(pattern)))
        r_ids = np.array([run_id_from_filepath(file) for file in files])

        files_mask = (r_id == r_ids)
        file_with_rid = files[files_mask]

        if len(file_with_rid) > 1:
            print(file_with_rid)
            raise ValueError(f"There are two data files with run ID {r_id:1.0f}")
        elif len(file_with_rid) == 1:
            file_with_rid = file_with_rid[0]
        
        if not file_with_rid:
            file_with_rid = recurse_find_data_file(r_id,days_ago+1)
    else:
        file_with_rid = recurse_find_data_file(r_id,days_ago+1)
    return file_with_rid

def all_glob_find_data_file(run_id):
    folderpath=os.path.join(DATA_DIR,'*','*.hdf5')
    list_of_files = glob.glob(folderpath)
    rids = [run_id_from_filepath(file) for file in list_of_files]
    rid_idx = rids.index(run_id)
    file = list_of_files[rid_idx]
    return file

def run_id_from_filepath(filepath):
    run_id = int(filepath.split("_")[DATA_DIR_FILE_DEPTH_IDX].split("\\")[-1])
    return run_id

def get_run_id():
    pwd = os.getcwd()
    os.chdir(DATA_DIR)
    with open(RUN_ID_PATH,'r') as f:
        rid = f.read()
    os.chdir(pwd)
    return int(rid)

def update_run_id(run_info):
    pwd = os.getcwd()
    os.chdir(DATA_DIR)

    line = f"{run_info.run_id + 1}"
    with open(RUN_ID_PATH,'w') as f:
        f.write(line)

    os.chdir(pwd)
