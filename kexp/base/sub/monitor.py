from pathlib import Path
from typing import Optional, List, Tuple
import os
import json
import time
import numpy as np
from artiq.language.core import kernel, kernel_from_string
from artiq.experiment import delay, EnvExperiment
from artiq.coredevice.core import Core

from kexp.control.artiq import DDS, DAC_CH, TTL_OUT, TTL_IN
from kexp.config.dds_id import dds_frame
from kexp.config.dac_id import dac_frame
from kexp.config.ttl_id import ttl_frame

class Monitor:
    """
    Detects changes in device state configuration and updates hardware devices.
    """
     
    def __init__(self, expt,
                  config_file: Optional[Path] = None):
        """
        Initialize the device state updater.
        
        Args:
            config_file: Path to device state config file. If None, uses default location.
        """
        if config_file is None:
            self.config_file = Path(os.getenv('code')) / 'k-exp' / \
                'kexp' / 'util' / 'device_state' / 'device_state_config.json'
        else:
            self.config_file = Path(config_file)
        
        self.last_config_data = None

        # Preallocate kernel function lists
        self.dds_frequency_amplitude_kernels = []
        self.dds_vpd_kernels = []
        self.dds_sw_state_kernels = []
        self.ttl_kernels = []
        self.dac_kernels = []

        self.clear_update_lists()

        self.expt = expt
        self.core: Core = expt.core
        self.dds: dds_frame = expt.dds 
        self.dac: dac_frame = expt.dac
        self.ttl: ttl_frame = expt.ttl

        self.build_device_lookup()

    def clear_update_lists(self):
        N = 100
        self.dds_frequency_amplitude_updates = [(-1, 0.0, 0.0)] * N
        self.dds_vpd_updates = [(-1, 0.0)] * N
        self.dds_sw_state_updates = [(-1, False)] * N
        self.ttl_updates = [(-1, False)] * N
        self.dac_updates = [(-1, 0.0)] * N
    
    def build_device_lookup(self):
        """Build lookup dictionaries and preallocate kernel function lists."""
        self.dds_dict = {}
        self.ttl_dict = {}
        self.dac_dict = {}

        # Build DDS device kernels
        for attr_name in dir(self.dds):
            if not attr_name.startswith('_'):
                attr_value = getattr(self.dds, attr_name)
                if isinstance(attr_value, DDS):
                    self.dds_dict[attr_name] = attr_value
                    self.dds_frequency_amplitude_kernels.append(kernel_from_string(
                        ["expt","f", "a"],
                        f"expt.dds.{attr_name}.set_dds(frequency=f, amplitude=a)"
                    ))
                    self.dds_vpd_kernels.append(kernel_from_string(
                        ["expt","v_pd_val"],
                        f"expt.dds.{attr_name}.set_dds(v_pd=v_pd_val)"
                    ))
                    self.dds_sw_state_kernels.append(kernel_from_string(
                        ["expt","state"],
                        f"expt.dds.{attr_name}.set_sw(state);"
                    ))

        # Build TTL device kernels
        for attr_name in dir(self.ttl):
            if not attr_name.startswith('_') and attr_name not in ['ttl_list', 'camera']:
                attr_value = getattr(self.ttl, attr_name)
                if isinstance(attr_value, (TTL_OUT)):
                    self.ttl_dict[attr_name] = attr_value
                    self.ttl_kernels.append(kernel_from_string(
                        ["expt","state"],
                        f"expt.ttl.{attr_name}.set_state(state)"
                    ))

        # Build DAC device kernels
        for attr_name in dir(self.dac):
            if not attr_name.startswith('_') and attr_name not in ['dac_device', 'dac_ch_list']:
                attr_value = getattr(self.dac, attr_name)
                if isinstance(attr_value, DAC_CH):
                    self.dac_dict[attr_name] = attr_value
                    self.dac_kernels.append(kernel_from_string(
                        ["expt","v"],
                        f"expt.dac.{attr_name}.set(v)"
                    ))

    def load_config_file(self) -> Optional[dict]:
        """Load configuration file and return data, retrying if file is in use."""
        max_attempts = 100
        wait_time = 0.05
        attempts = 0

        while attempts < max_attempts:
            try:
                if not self.config_file.exists():
                    print(f"Config file {self.config_file} does not exist")
                    return None

                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                # Check for file-in-use error (Windows: PermissionError, OSError with errno 13)
                if isinstance(e, PermissionError) or (hasattr(e, 'errno') and e.errno == 13):
                    attempts += 1
                    if attempts % 20 == 0:
                        print(f"Warning: Config file {self.config_file} is in use by another process (attempt {attempts})")
                    time.sleep(wait_time)
                    continue
                print(f"Error loading config file: {e}")
                return None
        print(f"Failed to load config file {self.config_file} after {max_attempts} attempts due to file being in use.")
        return None

    def detect_changes(self, verbose: bool = True) -> Tuple[
        List[Tuple[np.int32, float, float]],
        List[Tuple[np.int32, float]],
        List[Tuple[np.int32, np.int32]],
        List[Tuple[np.int32, np.int32]],
        List[Tuple[np.int32, float]]]:
        """
        Detect changes in the configuration file and populate update lists.
        
        Args:
            verbose: If True, print information about detected changes.
            
        Returns:
            Tuple of all update lists.
        """
        current_config = self.load_config_file()
        if current_config is None:
            if verbose:
                print("No changes detected (config file could not be loaded).")
            return (self.dds_frequency_amplitude_updates, self.dds_vpd_updates, 
                    self.dds_sw_state_updates, self.ttl_updates, self.dac_updates)

        self.clear_update_lists()

        if self.last_config_data is None:
            self.last_config_data = current_config
            if verbose:
                print("No changes detected (initial load).")
            return (self.dds_frequency_amplitude_updates, self.dds_vpd_updates, 
                    self.dds_sw_state_updates, self.ttl_updates, self.dac_updates)

        changes_detected = False

        # Process DDS devices
        old_dds = self.last_config_data.get('dds', {})
        new_dds = current_config.get('dds', {})
        for device_name, new_config in new_dds.items():
            if device_name not in self.dds_dict:
                continue
            old_config = old_dds.get(device_name, {})
            index = self.dds_frequency_amplitude_kernels.index(self.dds_frequency_amplitude_kernels[0])

            if old_config.get('frequency') != new_config.get('frequency') or \
            old_config.get('amplitude') != new_config.get('amplitude'):
                self.dds_frequency_amplitude_updates[index] = (
                    index, new_config['frequency'], new_config['amplitude'])
                changes_detected = True
                if verbose:
                    print(f"DDS {device_name}: Frequency/Amplitude changed to {new_config['frequency']}/{new_config['amplitude']}")

            if old_config.get('v_pd') != new_config.get('v_pd'):
                self.dds_vpd_updates[index] = (
                    index, new_config['v_pd']
                )
                changes_detected = True
                if verbose:
                    print(f"DDS {device_name}: V_PD changed to {new_config['v_pd']}")

            if old_config.get('sw_state') != new_config.get('sw_state'):
                self.dds_sw_state_updates[index] = (index, new_config['sw_state'])
                changes_detected = True
                if verbose:
                    print(f"DDS {device_name}: SW State changed to {new_config['sw_state']}")

        # Process TTL devices
        old_ttl = self.last_config_data.get('ttl', {})
        new_ttl = current_config.get('ttl', {})
        for device_name, new_config in new_ttl.items():
            if device_name not in self.ttl_dict:
                continue
            index = self.ttl_kernels.index(self.ttl_kernels[0])
            if old_ttl.get(device_name, {}).get('ttl_state') != new_config.get('ttl_state'):
                self.ttl_updates[index] = (index, new_config['ttl_state'])
                changes_detected = True
                if verbose:
                    print(f"TTL {device_name}: State changed to {new_config['ttl_state']}")

        # Process DAC devices
        old_dac = self.last_config_data.get('dac', {})
        new_dac = current_config.get('dac', {})
        for device_name, new_config in new_dac.items():
            if device_name not in self.dac_dict:
                continue
            index = self.dac_kernels.index(self.dac_kernels[0])
            if abs(old_dac.get(device_name, {}).get('voltage', 0.0) - new_config.get('voltage', 0.0)) > 1e-6:
                self.dac_updates[index] = (index, new_config['voltage'])
                changes_detected = True
                if verbose:
                    print(f"DAC {device_name}: Voltage changed to {new_config['voltage']}")

        self.last_config_data = current_config

        if verbose and not changes_detected:
            print("No changes detected.")

        return (self.dds_frequency_amplitude_updates, self.dds_vpd_updates, 
                self.dds_sw_state_updates, self.ttl_updates, self.dac_updates)

    @kernel
    def sync_change_list(self):
        """
        Synchronize kernel variables with the non-kernel update lists.
        """
        (self.dds_frequency_amplitude_updates, self.dds_vpd_updates, \
          self.dds_sw_state_updates, self.ttl_updates, self.dac_updates) = self.detect_changes()

    @kernel
    def apply_updates(self):
        """
        Apply the detected updates to the hardware devices.
        """
        index = -1
        f = 0.
        a = 0.
        v_pd = 0.
        sw_state = 0
        ttl_state = 0
        v = 0.
        N = len(self.dds_frequency_amplitude_updates)
        t0 = 8.e-9

        for i in range(N):
            index, f, a = self.dds_frequency_amplitude_updates[i]
            if index == -1:
                break
            self.dds_frequency_amplitude_kernels[index](self.expt,f, a)
            delay(t0)

        for i in range(N):
            index, v_pd = self.dds_vpd_updates[i]
            if index == -1:
                break
            self.dds_vpd_kernels[index](self.expt,v_pd)
            delay(t0)

        for i in range(N):
            index, sw_state = self.dds_sw_state_updates[i]
            if index == -1:
                break
            self.dds_sw_state_kernels[index](self.expt,bool(sw_state))
            delay(t0)

        for i in range(N):
            index, ttl_state = self.ttl_updates[i]
            if index == -1:
                break
            self.ttl_kernels[index](self.expt,bool(ttl_state))
            delay(t0)

        for i in range(N):
            index, v = self.dac_updates[i]
            if index == -1:
                break
            self.dac_kernels[index](self.expt,v)
            delay(t0)
            