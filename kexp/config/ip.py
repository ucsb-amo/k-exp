from pathlib import Path
import os

### monitor
MONITOR_SERVER_IP = "192.168.1.79"
MONITOR_SERVER_PORT = 6789
MONITOR_STATE_FILEPATH = os.path.join(os.getenv('data'),'device_state_config_testcrate.json')
MONITOR_EXPT_PATH = str( Path(os.getenv('code')) / 'k-exp' / 'kexp' / \
      'experiments' / 'tools' / 'monitor.py' )

### ethernet relay
ETHERNET_RELAY_IP = "192.168.1.109"
ETHERNET_RELAY_PORT = 2101