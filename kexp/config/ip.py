import os
from datetime import datetime
from waxa.data.server_talk import server_talk as st

from waxx.config.ip import EMAIL_CREDENTIALS_FILEPATH  # noqa: F401  (re-exported for kexp consumers)
INTERLOCK_EMAIL_CREDENTIALS_FILEPATH = r"G:\Shared drives\Tweezers\Environments and Profiles\interlock_gmail_credentials.txt"
# Remote Control's Google Voice number, notification addresses and whitelist, kept off GitHub
# (format: kexp.util.remote_control.rc_config)
REMOTE_CONTROL_CONFIG_FILEPATH = r"G:\Shared drives\Tweezers\Environments and Profiles\remote_control.json"

### data, filepaths
DATA_DIR = os.getenv("data")
_CODE_DIR = os.getenv("code")


def _safe_join(base, *parts):
    """os.path.join that tolerates a missing (None) base.

    On driveless client machines ``DATA_DIR`` / ``code`` may be unset; path
    constants below then resolve to ``None`` instead of raising at import,
    so client-only tooling (device control GUI, dashboards) imports cleanly.
    Consumers that actually need the path must check for ``None``.
    """
    if base is None:
        return None
    return os.path.join(base, *parts)


EXPT_PACKAGE_DIR = _safe_join(_CODE_DIR, "k-exp", "kexp")

### dashboard log directories
# Resolved lazily at use-site (see waxx.util.dashboard.logging_setup) so that
# tooling can run when DATA_DIR is unmapped.  The constants below may be None
# if the shared drive is not available; consumers must check and fall back.

LOG_DIR = _safe_join(DATA_DIR, "_logs")
SERVER_LOG_DIR = _safe_join(LOG_DIR, "server")
CLIENT_LOG_DIR = _safe_join(LOG_DIR, "client")
EXPT_PARAM_RELPATH = os.path.join("config","expt_params.py")
BASE_CLASS_RELPATH = os.path.join("base")  # all .py files in this directory will be saved
PATHS = (DATA_DIR, EXPT_PACKAGE_DIR, EXPT_PARAM_RELPATH, BASE_CLASS_RELPATH)

MAP_BAT_PATH = "\"G:\\Shared drives\\Weld Lab Shared Drive\\Infrastructure\\map_network_drives.bat\""
# MAP_BAT_PATH = "\"G:\Shared drives\Tweezers\Software\map_fake_network_drive.bat\""
FIRST_DATA_FOLDER_DATE = datetime(2023,6,22)

server_talk = st(data_dir=DATA_DIR,
                 run_id_relpath="run_id.py",
                 roi_spreadsheet_replath="roi.xlsx",
                 first_data_folder_date=FIRST_DATA_FOLDER_DATE,
                 on_data_dir_disconnected_bat_path=MAP_BAT_PATH)

### monitor
# Scope the monitor state file to the hardware id (last octet of core_addr from
# the device db at env var "db") so each server writes its own file without the
# path being hardcoded per branch.  Falls back to the default below when the id
# cannot be resolved (e.g. env var "db" unset).
from waxx.util.comms_server.hardware_id import get_hardware_id

_MONITOR_STATE_DEFAULT = _safe_join(DATA_DIR, 'device_state_config.json')
_monitor_hw_id = get_hardware_id()
MONITOR_STATE_FILEPATH = (
    _safe_join(DATA_DIR, f'device_state_config_{_monitor_hw_id}.json')
    if _monitor_hw_id is not None else _MONITOR_STATE_DEFAULT
)
# MONITOR_EXPT_PATH = str( Path(EXPT_PACKAGE_DIR) / 'experiments' / 'tools' / 'monitor.py' )
MONITOR_EXPT_PATH = _safe_join(EXPT_PACKAGE_DIR, 'experiments', 'tools', 'monitor.py')
# Run by the Device Control GUI's "Run MOT Observe" button (through the monitor
# server), e.g. when the device state is untrusted: its end state replaces the file.
RESET_STATE_EXPT_PATH = _safe_join(EXPT_PACKAGE_DIR, 'experiments', 'tools', 'mot_observe.py')
# Run back to back by the monitor server from the Device Control GUI's Composite
# tab (waxx.util.device_state.run_loop): key -> (card title, experiment file).
# Only these files can be looped -- plus, for 'expt_loop' (Sequences tab, file
# chosen at Start), any .py file under kexp/experiments except the monitor.
AUTO_TOF_EXPT_PATH = _safe_join(EXPT_PACKAGE_DIR, 'experiments', 'tools', 'auto_tof.py')
EXPT_LOOP_ROOT = _safe_join(EXPT_PACKAGE_DIR, 'experiments')
# The BEC TOF loop's scan, set from its card (⚙; waxx.util.device_state.loop_scan):
# bounds and the defaults it starts with after a monitor server restart (SI).
AUTO_TOF_SCAN = {'xvar': 't_tof', 'unit': 'ms', 'scale': 1.e-3,
                 'minimum': 0., 'maximum': 25.e-3,
                 'start': 1.e-3, 'stop': 4.e-3, 'n': 9, 'repeats': 5}
RUN_LOOP_EXPTS = {'auto_tof': ('BEC TOF loop', AUTO_TOF_EXPT_PATH, AUTO_TOF_SCAN),
                  'expt_loop': {'title': 'Experiment loop', 'root': EXPT_LOOP_ROOT,
                                'exclude': (MONITOR_EXPT_PATH,)}}

### SRS control servers
SRS_CONTROL_IP = "192.168.1.76"
SRS_DC205_SERVER_PORT = 5555
SRS_DC205_COM = 'COM10'
SRS_SR560_SERVER_PORT = 5556
SRS_SR560_COM = 'COM9'

### ethernet relay
ETHERNET_RELAY_IP = "192.168.1.109"
ETHERNET_RELAY_PORT = 2101

### ALS server
ALS_COM = 'COM6'

### Precilaser server
PRECILASER_COM = 'COM20'

###
MAGNETOMETER_COM = 'COM33'
MAGNETOMETER_REFERENCE_CSV_PATH = _safe_join(DATA_DIR, 'magnetometer_reference.csv')

### Interlock controller
INTERLOCK_COM = 'COM5'

###
WAVEMETER_MOGLABS_IP = '192.168.1.94'

### Bristol wavemeter
BRISTOL_WAVEMETER_IP = '192.168.1.105'

### Keysight DC current supplies — (max_current_A, ip)
KEYSIGHT_SUPPLIES = [
    (170, '192.168.1.77'),
    (500, '192.168.1.78'),
]

### kinesis motors
DEVICE_ID_KINESIS_REF_BEAM_WAVEPLATE_ROTATOR = 27500961

### PDXC picomotor controller (kong, 192.168.1.76)
PDXC_SERVER_IP = "192.168.1.76"   # kong
PDXC_COM = "COM40"

### Tweezer AWG (Spectrum DN2 netbox; takes one connection at a time -- held by
### the monitor server between runs, see kexp.config.monitor_connections)
AWG_IP = 'TCPIP::192.168.1.83::inst0::INSTR'

### remote control
# The old whitelist file, read once to move its entries into REMOTE_CONTROL_CONFIG_FILEPATH
WHITELIST_PATH = (
    os.path.join(DATA_DIR, "remote_whitelist.json")
    if DATA_DIR
    else os.path.join(os.path.dirname(__file__), "remote_whitelist.json")
)