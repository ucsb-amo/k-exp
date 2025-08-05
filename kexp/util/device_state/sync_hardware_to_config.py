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
from kexp import Base
from artiq.language.core import kernel_from_string

# Import device classes
try:
    from kexp.control.artiq.DDS import DDS
    from kexp.control.artiq.DAC_CH import DAC_CH
    from kexp.control.artiq.TTL import TTL, TTL_OUT, TTL_IN
except ImportError as e:
    print(f"Error importing device classes: {e}")
    raise

class DeviceStateUpdater:
    """
    Detects changes in device state configuration and updates hardware devices.
    """
    
    def __init__(self, base_obj: Base, config_file: Optional[Path] = None):
        """
        Initialize the device state updater.
        
        Args:
            base_obj: Instance of kexp.base.Base with .dac, .dds, .ttl attributes
            config_file: Path to device state config file. If None, uses default location.
        """
        self.base_obj = base_obj
        
        if config_file is None:
            self.config_file = Path(os.getenv('code')) / 'k-exp' \
                'kexp' / 'util' / 'device_state' / 'device_state_config.json'
        else:
            self.config_file = Path(config_file)
        
        # Store last known state for change detection
        self.last_config_data = None

        self._update_kernels_2var = [kernel_from_string(["self","name","v1","v2"],"pass")]*1000
        self.changes = 0
        
        # Device lookup dictionaries for faster access
        self._build_device_lookup()
    
    def _build_device_lookup(self):
        """Build lookup dictionaries for quick device access by name."""
        self.dds_devices = {}
        self.ttl_devices = {}
        self.dac_devices = {}
        
        # Build DDS device lookup
        for attr_name in dir(self.base_obj.dds):
            if not attr_name.startswith('_'):
                attr_value = getattr(self.base_obj.dds, attr_name)
                if isinstance(attr_value, DDS):
                    self.dds_devices[attr_name] = attr_value
        
        # Build TTL device lookup
        for attr_name in dir(self.base_obj.ttl):
            if not attr_name.startswith('_') and attr_name not in ['ttl_list', 'camera']:
                attr_value = getattr(self.base_obj.ttl, attr_name)
                if isinstance(attr_value, (TTL_OUT, TTL_IN)):
                    self.ttl_devices[attr_name] = attr_value
        
        # Build DAC device lookup
        for attr_name in dir(self.base_obj.dac):
            if not attr_name.startswith('_') and attr_name not in ['dac_device', 'dac_ch_list']:
                attr_value = getattr(self.base_obj.dac, attr_name)
                if isinstance(attr_value, DAC_CH):
                    self.dac_devices[attr_name] = attr_value
    
    def _load_config_file(self) -> Optional[Dict[str, Any]]:
        """Load configuration file and return data."""
        try:
            if not self.config_file.exists():
                print(f"Config file {self.config_file} does not exist")
                return None
            
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config file: {e}")
            return None
    
    def detect_changes(self, verbose: bool = True) -> Tuple[Dict[str, Dict[str, Any]], 
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
        current_config = self._load_config_file()
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
            if device_name not in self.dds_devices:
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
                    print(f"DDS {device_name} frequency: {old_config.get('frequency')} -> {new_config['frequency']}")
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
            if device_name not in self.ttl_devices:
                if verbose:
                    print(f"Warning: TTL device '{device_name}' not found in base object")
                continue
                
            # Only process TTL_OUT devices
            if not isinstance(self.ttl_devices[device_name], TTL_OUT):
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
            if device_name not in self.dac_devices:
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
        
        return dds_updates, ttl_updates, dac_updates
    
    def generate_update_kernels(self, dds_updates: Dict[str, Dict[str, Any]], 
                     ttl_updates: Dict[str, Dict[str, Any]], 
                     dac_updates: Dict[str, Dict[str, Any]], 
                     verbose: bool = True) -> bool:
        """
        Apply the detected updates to the hardware devices.
        
        Args:
            dds_updates: Dict mapping DDS device names to their update parameters
            ttl_updates: Dict mapping TTL device names to their update parameters  
            dac_updates: Dict mapping DAC device names to their update parameters
        """

        self.changes = 0

        # Apply DDS updates
        for device_name, updates in dds_updates.items():
            device = self.dds_devices[device_name]
            
            # Update frequency and/or amplitude using set method
            if 'frequency' in updates or 'amplitude' in updates:
                frequency = updates.get('frequency', device.frequency)
                amplitude = updates.get('amplitude', device.amplitude)

                self.change_kernel_list[self.changes] = \
                    kernel_from_string(["self","name","v1","v2"],\
                        f"self.dds.name.dds_device.set(frequency=f, amplitude=a)")
                self.changes += 1
            
            # Update v_pd using DAC write
            if 'v_pd' in updates:
                v_pd = updates['v_pd']
                self.change_kernel_list[self.changes] = \
                    kernel_from_string(["self"],\
                        f"self.dds.{device_name}.dac_device.write_dac(channel=self.dds.{device_name}.dac_ch, voltage={v_pd})")
                self.changes += 1
            
            # Update state using switch on/off
            if 'state' in updates:
                state = updates['state']
                if state:
                    fcn = "on"
                else:
                    fcn = "off"
                self.change_kernel_list[self.changes] = \
                    kernel_from_string(["self"],\
                        f"self.dds.{device_name}.dds_device.sw.{fcn}()")
                self.changes += 1
        
        # Apply TTL updates
        for device_name, updates in ttl_updates.items():
            device = self.ttl_devices[device_name]
        
            # Update state using on/off methods
            if 'state' in updates:
                state = updates['state']
                if state:
                    fcn = "on"
                else:
                    fcn = "on"
                self.change_kernel_list[self.changes] = \
                    kernel_from_string(["self"],\
                        f"self.ttl.{device_name}.{fcn}()")
                self.changes += 1
        
        # Apply DAC updates
        for device_name, updates in dac_updates.items():
            device = self.dac_devices[device_name]
            
            # Update voltage using DAC write
            if 'voltage' in updates:
                voltage = updates['voltage']
                device.dac_device.write_dac(channel=device.ch, voltage=voltage)
                self.change_kernel_list[self.changes] = \
                    kernel_from_string(["self"],\
                        f"self.dac.{device_name}.dac_device.write_dac(channel=self.dac.{device_name}.ch, voltage={v_pd})")
                self.changes += 1
    
    def check_and_update_devices(self, verbose: bool = True) -> bool:
        """
        Combined method to detect changes and apply updates.
        
        Args:
            verbose: If True, print detailed information
            
        Returns:
            bool: True if any devices were updated successfully, False otherwise
        """
        # Detect changes
        dds_updates, ttl_updates, dac_updates = self.detect_changes(verbose=verbose)
        
        # Check if there are any updates to apply
        if not (dds_updates or ttl_updates or dac_updates):
            return False
        
        # Apply updates
        success = self.apply_updates(dds_updates, ttl_updates, dac_updates, verbose=verbose)
        
        if verbose:
            if success:
                print("All device updates completed successfully")
            else:
                print("Some device updates failed")
        
        return success
    
    def start_monitoring(self, check_interval: float = 1.0, verbose: bool = True):
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
            while True:
                self.check_and_update_devices(verbose=verbose)
                time.sleep(check_interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print(f"Error during monitoring: {e}")

# Convenience functions for easy use
def detect_device_changes(base_obj, config_file: Optional[Path] = None, 
                         verbose: bool = True) -> Tuple[Dict[str, Dict[str, Any]], 
                                                       Dict[str, Dict[str, Any]], 
                                                       Dict[str, Dict[str, Any]]]:
    """
    Convenience function to detect device configuration changes.
    
    Args:
        base_obj: Instance of kexp.base.Base with device frames
        config_file: Path to config file (optional)
        verbose: Whether to print detailed information
        
    Returns:
        Tuple of (dds_updates, ttl_updates, dac_updates)
    """
    updater = DeviceStateUpdater(base_obj, config_file)
    return updater.detect_changes(verbose=verbose)

def apply_device_updates(base_obj, dds_updates: Dict[str, Dict[str, Any]], 
                        ttl_updates: Dict[str, Dict[str, Any]], 
                        dac_updates: Dict[str, Dict[str, Any]], 
                        verbose: bool = True) -> bool:
    """
    Convenience function to apply device updates.
    
    Args:
        base_obj: Instance of kexp.base.Base with device frames
        dds_updates: DDS device updates
        ttl_updates: TTL device updates
        dac_updates: DAC device updates
        verbose: Whether to print detailed information
        
    Returns:
        bool: True if all updates successful
    """
    updater = DeviceStateUpdater(base_obj)
    return updater.apply_updates(dds_updates, ttl_updates, dac_updates, verbose=verbose)

def check_and_update_devices(base_obj, config_file: Optional[Path] = None, 
                           verbose: bool = True) -> bool:
    """
    Convenience function to check for changes and update devices.
    
    Args:
        base_obj: Instance of kexp.base.Base with device frames
        config_file: Path to config file (optional)
        verbose: Whether to print detailed information
        
    Returns:
        bool: True if any devices were updated
    """
    updater = DeviceStateUpdater(base_obj, config_file)
    return updater.check_and_update_devices(verbose=verbose)

# Example usage
if __name__ == "__main__":
    print("This module provides device state change detection and updating.")
    print("Usage examples:")
    print("")
    print("# Two-step process:")
    print("updater = DeviceStateUpdater(your_base_object)")
    print("dds_updates, ttl_updates, dac_updates = updater.detect_changes()")
    print("updater.apply_updates(dds_updates, ttl_updates, dac_updates)")
    print("")
    print("# Combined process:")
    print("updater.check_and_update_devices()")
    print("")
    print("# Convenience functions:")
    print("from kexp.util.device_state.device_updater import check_and_update_devices")
    print("check_and_update_devices(your_base_object)")