#!/usr/bin/env python3
"""
Device state change detector and updater.

This module provides functionality to detect changes in device_state_config.json
and apply those changes to the corresponding hardware devices using the
appropriate device-specific methods.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime
import hashlib
import os
from artiq.language.core import kernel_from_string, now_mu
from artiq.experiment import kernel, delay

# Import device classes
try:
    from kexp.control.artiq.DDS import DDS
    from kexp.control.artiq.DAC_CH import DAC_CH
    from kexp.control.artiq.TTL import TTL, TTL_OUT, TTL_IN
    from kexp.config.dds_id import dds_frame
    from kexp.config.dac_id import dac_frame
    from kexp.config.ttl_id import ttl_frame
except ImportError as e:
    print(f"Error importing device classes: {e}")
    raise

class Monitor():
    """
    Detects changes in device state configuration and updates hardware devices.
    """
    
    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize the device state updater.
        
        Args:
            base_obj: Instance of kexp.base.Base with .dac, .dds, .ttl attributes
            config_file: Path to device state config file. If None, uses default location.
        """
        
        if config_file is None:
            self.config_file = Path(os.getenv('code')) / 'k-exp' / \
                'kexp' / 'util' / 'device_state' / 'device_state_config.json'
        else:
            self.config_file = Path(config_file)
        
        # Store last known state for change detection
        self.last_config_data = None

        self._kernel_set_dds = kernel_from_string(["self","device","f","a"],\
                                                  "device.dds_device.set(frequency=f, amplitude=a)")
        self._kernel_set_dds_dac = kernel_from_string(["self","device","v"],\
                                                      "device.dac_device.write_dac(channel=device.key.dac_ch, voltage=v)")
        self._kernel_set_dds_sw = kernel_from_string(["self","device","state"],\
                        f"device.dds_device.sw.set_o(state)")
        self._kernel_set_ttl = kernel_from_string(["self","device","state"],\
                        f"device.set_o(state)")
        self._kernel_set_dac = kernel_from_string(["self","device","v"],\
                        f"device.dac_device.write_dac(channel=device.ch, voltage=v)")
        
        # Device lookup dictionaries for faster access
        self.__build_device_lookup()
    
    def __build_device_lookup(self):
        """Build lookup dictionaries for quick device access by name."""
        self.__dds_dict = {}
        self.__ttl_dict = {}
        self.__dac_dict = {}
        
        # Build DDS device lookup
        for attr_name in dir(self.dds):
            if not attr_name.startswith('_'):
                attr_value = getattr(self.dds, attr_name)
                if isinstance(attr_value, DDS):
                    self.__dds_dict[attr_name] = attr_value
        
        # Build TTL device lookup
        for attr_name in dir(self.ttl):
            if not attr_name.startswith('_') and attr_name not in ['ttl_list', 'camera']:
                attr_value = getattr(self.ttl, attr_name)
                if isinstance(attr_value, (TTL_OUT, TTL_IN)):
                    self.__ttl_dict[attr_name] = attr_value
        
        # Build DAC device lookup
        for attr_name in dir(self.dac):
            if not attr_name.startswith('_') and attr_name not in ['dac_device', 'dac_ch_list']:
                attr_value = getattr(self.dac, attr_name)
                if isinstance(attr_value, DAC_CH):
                    self.__dac_dict[attr_name] = attr_value
    
    def __load_config_file(self) -> Optional[Dict[str, Any]]:
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
    
    def __detect_changes(self, verbose: bool = False) -> Tuple[Dict[str, Dict[str, Any]], 
                                                           Dict[str, Dict[str, Any]], 
                                                           Dict[str, Dict[str, Any]]]:
        """
        Detect changes in the configuration file and return parameters to be updated.
        
        Args:
            verbose: If True, print information about detected changes
            
        Returns:
            Tuple of (dds_updates, ttl_updates, dac_updates) where each is a dict
            mapping device names to their parameters that need updating.
        """
        # Load current configuration
        current_config = self.__load_config_file()
        if current_config is None:
            return {}, {}, {}
        
        # Initialize update dictionaries
        dds_updates = {}
        ttl_updates = {}
        dac_updates = {}
        
        # Check if this is the first run
        if self.last_config_data is None:
            if verbose:
                print("First run - storing initial configuration state")
            self.last_config_data = current_config
            return dds_updates, ttl_updates, dac_updates
        
        # Process DDS devices
        old_dds = self.last_config_data.get('dds', {})
        new_dds = current_config.get('dds', {})
        
        for device_name in new_dds.keys():
            if device_name not in self.__dds_dict:
                if verbose:
                    print(f"Warning: DDS device '{device_name}' not found in base object")
                continue
                
            old_config = old_dds.get(device_name, {})
            new_config = new_dds[device_name]
            
            device_updates = {}
            
            # Check frequency/amplitude changes
            freq_changed = old_config.get('frequency') != new_config.get('frequency')
            amp_changed = old_config.get('amplitude') != new_config.get('amplitude')
            if freq_changed or amp_changed:
                device_updates['frequency'] = new_config['frequency']
                device_updates['amplitude'] = new_config['amplitude']
                if verbose:
                    if freq_changed:
                        print(f"DDS {device_name} frequency: {old_config.get('frequency')} -> {new_config['frequency']}")
                    if amp_changed:
                        print(f"DDS {device_name} amplitude: {old_config.get('amplitude')} -> {new_config['amplitude']}")
            
            # Check v_pd changes
            if old_config.get('v_pd') != new_config.get('v_pd'):
                device_updates['v_pd'] = new_config['v_pd']
                if verbose:
                    print(f"DDS {device_name} v_pd: {old_config.get('v_pd')} -> {new_config['v_pd']}")
            
            # Check state changes
            if old_config.get('state') != new_config.get('state'):
                device_updates['state'] = new_config['state']
                if verbose:
                    print(f"DDS {device_name} state: {old_config.get('state')} -> {new_config['state']}")
            
            if device_updates:
                dds_updates[device_name] = device_updates
        
        # Process TTL devices
        old_ttl = self.last_config_data.get('ttl', {})
        new_ttl = current_config.get('ttl', {})
        
        for device_name in new_ttl.keys():
            if device_name not in self.__ttl_dict:
                if verbose:
                    print(f"Warning: TTL device '{device_name}' not found in base object")
                continue
                
            # Only process TTL_OUT devices
            if not isinstance(self.__ttl_dict[device_name], TTL_OUT):
                continue
                
            old_config = old_ttl.get(device_name, {})
            new_config = new_ttl[device_name]
            
            device_updates = {}
            
            # Check state changes
            if old_config.get('state') != new_config.get('state'):
                device_updates['state'] = new_config['state']
                if verbose:
                    print(f"TTL {device_name} state: {old_config.get('state')} -> {new_config['state']}")
            
            if device_updates:
                ttl_updates[device_name] = device_updates
        
        # Process DAC devices
        old_dac = self.last_config_data.get('dac', {})
        new_dac = current_config.get('dac', {})
        
        for device_name in new_dac.keys():
            if device_name not in self.__dac_dict:
                if verbose:
                    print(f"Warning: DAC device '{device_name}' not found in base object")
                continue
                
            old_config = old_dac.get(device_name, {})
            new_config = new_dac[device_name]
            
            device_updates = {}
            
            # Check voltage changes (use small epsilon for float comparison)
            old_voltage = old_config.get('voltage', 0.0)
            new_voltage = new_config.get('voltage', 0.0)
            if abs(old_voltage - new_voltage) > 1e-6:
                device_updates['voltage'] = new_voltage
                if verbose:
                    print(f"DAC {device_name} voltage: {old_voltage} -> {new_voltage}")
            
            if device_updates:
                dac_updates[device_name] = device_updates
        
        # Update stored state
        self.last_config_data = current_config
        
        if verbose and (dds_updates or ttl_updates or dac_updates):
            total_updates = len(dds_updates) + len(ttl_updates) + len(dac_updates)
            print(f"Detected changes in {total_updates} devices")
        elif verbose:
            print("No device changes detected")
            pass
        
        return dds_updates, ttl_updates, dac_updates

    @kernel
    def __set_dds(self,device_obj,frequency,amplitude):
        self._kernel_set_dds(self,device_obj,frequency,amplitude)
        pass

    @kernel
    def __set_dds_vpd(self,device_obj,v_pd):
        self._kernel_set_dds_dac(self,device_obj,v_pd)
        pass

    @kernel
    def __set_dds_sw(self,device_obj,state):
        self._kernel_set_dds_sw(self,device_obj,bool(state))
        pass

    @kernel
    def __set_ttl(self,device_obj,state):
        self._kernel_set_ttl(self,device_obj,bool(state))
        pass

    @kernel
    def __set_dac(self,device_obj,v):
        self._kernel_set_dac(self,device_obj,v)
        pass
    
    def __apply_updates(self, 
                        dds_updates: Dict[str, Dict[str, Any]], 
                        ttl_updates: Dict[str, Dict[str, Any]], 
                        dac_updates: Dict[str, Dict[str, Any]]):
        """
        Apply the detected updates to the hardware devices.
        
        Args:
            dds_updates: Dict mapping DDS device names to their update parameters
            ttl_updates: Dict mapping TTL device names to their update parameters  
            dac_updates: Dict mapping DAC device names to their update parameters
        """

        # Apply DDS updates
        for name, updates in dds_updates.items():
            device = self.__dds_dict[name]
            
            # Update frequency and/or amplitude using set method
            if 'frequency' in updates or 'amplitude' in updates:
                frequency = updates.get('frequency', device.frequency)
                amplitude = updates.get('amplitude', device.amplitude)
                self.__set_dds(self,device,frequency,amplitude)

            # Update v_pd using DAC write
            if 'v_pd' in updates:
                v_pd = updates['v_pd']
                self.__set_dds_vpd(self,device,v_pd)
            
            # Update state using switch on/off
            if 'state' in updates:
                state = updates['state']
                self.__set_dds_sw(self,device,state)
        
        # Apply TTL updates
        for name, updates in ttl_updates.items():
            device = self.__ttl_dict[name]
        
            # Update state using on/off methods
            if 'state' in updates:
                state = updates['state']
                self.__set_ttl(self,device,state)
        
        # Apply DAC updates
        for name, updates in dac_updates.items():
            device = self.__dac_dict[name]
            
            # Update voltage using DAC write
            if 'voltage' in updates:
                voltage = updates['voltage']
                self.__set_dac(self,device,voltage)
    
    def check_and_update_devices(self, verbose: bool = False):
        """
        Combined method to detect changes and apply updates.
        
        Args:
            verbose: If True, print detailed information
            
        Returns:
            bool: True if any devices were updated successfully, False otherwise
        """
        # Detect changes
        dds_updates, ttl_updates, dac_updates = self.__detect_changes(verbose=verbose)
        
        # Check if there are any updates to apply
        if not (dds_updates or ttl_updates or dac_updates):
            self.__apply_updates(dds_updates, ttl_updates, dac_updates)

    @kernel
    def __start_monitoring_kernel(self,check_interval,verbose):
        while True:
            self.core.wait_until_mu(now_mu())
            delay(check_interval)
            self.check_and_update_devices()
        
    
    def start_monitoring(self, check_interval: float = 0.5, verbose: bool = False):
        """
        Start continuous monitoring of the configuration file.
        
        Args:
            check_interval: Time in seconds between checks
            verbose: If True, print detailed information
        """
        print(f"Starting device state monitoring (checking every {check_interval}s)")
        print(f"Monitoring file: {self.config_file}")
        print("Press Ctrl+C to stop")
        
        try:
            self.__start_monitoring_kernel(check_interval,verbose)
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print("Error during monitoring:")
            print(e)