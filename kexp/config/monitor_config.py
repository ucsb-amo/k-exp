from pathlib import Path
import os

MONITOR_SERVER_IP = "192.168.1.76"
MONITOR_SERVER_PORT = 6789
MONITOR_STATE_FILEPATH = os.path.join(os.getenv('data'),'device_state_config.json')
MONITOR_EXPT_PATH = str( Path(os.getenv('code')) / 'k-exp' / 'kexp' / \
      'experiments' / 'tools' / 'monitor.py' )