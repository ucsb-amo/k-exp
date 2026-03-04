import os
from datetime import datetime
from waxa.data.server_talk import server_talk as st

### data, filepaths
# DATA_DIR = os.getenv("data")
DATA_DIR = 'Z:\_K\PotassiumData'
EXPT_PACKAGE_DIR = os.path.join(os.getenv("code"),"k-exp","kexp")
EXPT_PARAM_RELPATH = os.path.join("config","expt_params.py")
COOLING_RELPATH = os.path.join("base","cooling.py")
IMAGING_RELPATH = os.path.join("base","image.py")
PATHS = (DATA_DIR, EXPT_PACKAGE_DIR, EXPT_PARAM_RELPATH, COOLING_RELPATH, IMAGING_RELPATH)

# MAP_BAT_PATH = "\"G:\\Shared drives\\Weld Lab Shared Drive\\Infrastructure\\map_network_drives_PeterRecommended.bat\""
MAP_BAT_PATH = "\"G:\Shared drives\Tweezers\Software\map_fake_network_drive.bat\""
FIRST_DATA_FOLDER_DATE = datetime(2023,6,22)

server_talk = st(data_dir=DATA_DIR,
                 run_id_relpath="run_id.py",
                 roi_spreadsheet_replath="roi.xlsx",
                 first_data_folder_date=FIRST_DATA_FOLDER_DATE,
                 on_data_dir_disconnected_bat_path=MAP_BAT_PATH)

### monitor
MONITOR_SERVER_IP = "192.168.1.76"
# MONITOR_SERVER_IP = "192.168.1.79"
MONITOR_SERVER_PORT = 6789
MONITOR_STATE_FILEPATH = os.path.join(DATA_DIR,'device_state_config.json')
# MONITOR_EXPT_PATH = str( Path(EXPT_PACKAGE_DIR) / 'experiments' / 'tools' / 'monitor.py' )
MONITOR_EXPT_PATH = os.path.join(EXPT_PACKAGE_DIR,'experiments','tools','monitor.py')

### SRS control servers
SRS_CONTROL_IP = "192.168.1.76"
SRS_DC205_SERVER_PORT = 5555
SRS_DC205_COM = 'COM10'
SRS_SR560_SERVER_PORT = 5556
SRS_SR560_COM = 'COM9'

### ethernet relay
ETHERNET_RELAY_IP = "192.168.1.109"
ETHERNET_RELAY_PORT = 2101

### kinesis motors
DEVICE_ID_KINESIS_REF_BEAM_WAVEPLATE_ROTATOR = 27500961