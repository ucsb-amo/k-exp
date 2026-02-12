from pathlib import Path
import os

### data, filepaths
DATA_DIR = os.getenv("data")
EXPT_PACKAGE_DIR = os.path.join(os.getenv("code"),"k-exp","kexp")
EXPT_PARAM_RELPATH = os.path.join("config","expt_params.py")
COOLING_RELPATH = os.path.join("base","cooling.py")
IMAGING_RELPATH = os.path.join("base","image.py")
PATHS = (DATA_DIR, EXPT_PACKAGE_DIR, EXPT_PARAM_RELPATH, COOLING_RELPATH, IMAGING_RELPATH)

### monitor
MONITOR_SERVER_IP = "192.168.1.76"
# MONITOR_SERVER_IP = "192.168.1.79"
MONITOR_SERVER_PORT = 6789
MONITOR_STATE_FILEPATH = os.path.join(DATA_DIR,'device_state_config.json')
MONITOR_EXPT_PATH = str( Path(EXPT_PACKAGE_DIR) / 'experiments' / 'tools' / 'monitor.py' )

### SRS control servers
SRS_CONTROL_IP = "192.168.1.76"
SRS_DC205_SERVER_PORT = 5555
SRS_DC205_COM = 'COM10'
SRS_SR560_SERVER_PORT = 5556
SRS_SR560_COM = 'COM9'

### ethernet relay
ETHERNET_RELAY_IP = "192.168.1.109"
ETHERNET_RELAY_PORT = 2101