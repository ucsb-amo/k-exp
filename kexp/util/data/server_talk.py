import os
import subprocess
from datetime import datetime, timedelta
import glob

DATA_DIR = os.getenv("data")
MAP_BAT_PATH = "\"G:\\Shared drives\\Weld Lab Shared Drive\\Infrastructure\\map_network_drives_PeterRecommended.bat\""

def check_for_mapped_data_dir(data_dir=DATA_DIR):
    if not os.path.exists(data_dir):
        print(f"Data dir ({data_dir}) not found. Attempting to re-map network drives.")
        cmd = MAP_BAT_PATH         
        result = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        if not os.path.exists(data_dir):
            raise ValueError(f"Data dir still not found. Are you connected to the physics network?") 
        else:
            print("Network drives successfully mapped.")

def get_latest_date_folder(days_ago):
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