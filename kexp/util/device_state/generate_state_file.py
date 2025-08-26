#!/usr/bin/env python3
"""
Script to generate device state configuration files from _id files.

This script reads all *_id.py files in the config folder (except camera_id.py),
extracts devices that are assigned using the assign methods, and creates a
configuration file organized by device type (DDS, TTL, DAC) with current
state values for each device.

For DDS devices: frequency, amplitude, v_pd (voltage), sw_state, and state (on/off)
For TTL devices: state (on/off)  
For DAC devices: voltage
"""

import os
import sys
import importlib.util
import json
import numpy as np
from pathlib import Path
from typing import Dict, Any, List

# Add the k-exp package to the path
script_dir = Path(__file__).parent
kexp_root = Path(os.getenv('code')) / 'k-exp'
sys.path.insert(0, str(kexp_root))

# Import device classes for isinstance checks
try:
    from kexp.control.artiq.DDS import DDS
    from kexp.control.artiq.DAC_CH import DAC_CH
    from kexp.control.artiq.TTL import TTL, TTL_OUT, TTL_IN
except ImportError as e:
    print(f"Error importing device classes: {e}")
    print("Make sure the kexp package is available in the Python path")
    sys.exit(1)

def load_module_from_file(file_path: Path):
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location("module", file_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def extract_dds_devices(frame_obj) -> Dict[str, Dict[str, Any]]:
    """Extract DDS device states from a dds_frame object."""
    devices = {}
    
    # Iterate over _dds_list to extract DDS devices
    dds_list = getattr(frame_obj, 'dds_list', [])
    for dds_device in dds_list:
        if isinstance(dds_device, DDS):
            sw_state = getattr(dds_device, 'sw_state', 0)
            devices[dds_device.key] = {
                'frequency': getattr(dds_device, 'frequency', 0.0),
                'amplitude': getattr(dds_device, 'amplitude', 0.0),
                'v_pd': getattr(dds_device, 'v_pd', 0.0),  # voltage photodiode setpoint
                'urukul_idx': getattr(dds_device, 'urukul_idx', 0),
                'ch': getattr(dds_device, 'ch', 0),
                'sw_state': sw_state,  # Hardware switch state (0/1)
                'transition': getattr(dds_device, 'transition', 'None'),
                'aom_order': getattr(dds_device, 'aom_order', 0),
                'dac_ch': getattr(dds_device, 'dac_ch', -1)
            }
    
    return devices

def extract_ttl_devices(frame_obj) -> Dict[str, Dict[str, Any]]:
    """Extract TTL device states from a ttl_frame object."""
    devices = {}
    
    # Iterate over _ttl_list to extract TTL devices
    ttl_list = getattr(frame_obj, 'ttl_list', [])
    for ttl_device in ttl_list:
        if isinstance(ttl_device, TTL_OUT):
            # Determine the specific TTL type
            ttl_type = 'out'
            # if isinstance(ttl_device, TTL_IN):
            #     ttl_type = 'in'
            # elif isinstance(ttl_device, TTL_OUT):
            #     ttl_type = 'out'
            
            # Get actual state from the TTL object
            ttl_state = getattr(ttl_device, 'state', 0)
            
            devices[ttl_device.key] = {
                'ch': getattr(ttl_device, 'ch', 0),
                'ttl_state': ttl_state,  # Raw state value (0/1)
                'type': ttl_type
            }
    
    return devices

def extract_dac_devices(frame_obj) -> Dict[str, Dict[str, Any]]:
    """Extract DAC device states from a dac_frame object."""
    devices = {}
    
    # Iterate over _dac_ch_list to extract DAC devices
    dac_ch_list = getattr(frame_obj, 'dac_ch_list', [])
    for dac_device in dac_ch_list:
        if isinstance(dac_device, DAC_CH):
            devices[dac_device.key] = {
                'ch': getattr(dac_device, 'ch', 0),
                'voltage': getattr(dac_device, 'v', 0.0),
                'max_voltage': getattr(dac_device, 'max_v', 9.99)
            }
    
    return devices

def generate_device_config():
    """Generate device configuration from all _id files."""
    
    # Path to config directory
    config_dir = kexp_root / 'kexp' / 'config'
    
    if not config_dir.exists():
        print(f"Config directory not found: {config_dir}")
        return None
    
    # Find all _id files except camera_id
    id_files = [f for f in config_dir.glob('*_id.py') if f.name != 'camera_id.py']
    
    device_config = {
        'dds': {},
        'ttl': {},
        'dac': {},
        'metadata': {
            'generated_from': [str(f.relative_to(config_dir)) for f in id_files],
            'timestamp': None
        }
    }
    
    for id_file in id_files:
        print(f"Processing {id_file.name}...")
        
        # Load the module
        module = load_module_from_file(id_file)
        if module is None:
            continue
        
        try:
            # Determine the device type and extract devices
            if 'dds_id' in id_file.name:
                # Create frame object to access assigned devices
                if hasattr(module, 'dds_frame'):
                    frame = module.dds_frame()
                    dds_devices = extract_dds_devices(frame)
                    device_config['dds'].update(dds_devices)
                    print(f"  Found {len(dds_devices)} DDS devices")
                    
            elif 'ttl_id' in id_file.name:
                if hasattr(module, 'ttl_frame'):
                    frame = module.ttl_frame()
                    ttl_devices = extract_ttl_devices(frame)
                    device_config['ttl'].update(ttl_devices)
                    print(f"  Found {len(ttl_devices)} TTL devices")
                    
            elif 'dac_id' in id_file.name:
                if hasattr(module, 'dac_frame'):
                    frame = module.dac_frame()
                    dac_devices = extract_dac_devices(frame)
                    device_config['dac'].update(dac_devices)
                    print(f"  Found {len(dac_devices)} DAC devices")
                    
        except Exception as e:
            print(f"  Error processing {id_file.name}: {e}")
            continue
    
    # Add timestamp
    from datetime import datetime
    device_config['metadata']['timestamp'] = datetime.now().isoformat()
    
    return device_config

def save_config_file(config_data: Dict, output_file: str = None):
    """Save the configuration data to a JSON file."""
    if output_file is None:
        output_file = script_dir / 'device_state_config.json'
    else:
        output_file = Path(output_file)
    
    # Helper function to convert numpy types to native Python types
    def convert_numpy_types(obj):
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    try:
        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent=2, sort_keys=True, default=convert_numpy_types)
        print(f"\nConfiguration saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error saving configuration file: {e}")
        return None

def print_summary(config_data: Dict):
    """Print a summary of the generated configuration."""
    print("\n" + "="*60)
    print("DEVICE CONFIGURATION SUMMARY")
    print("="*60)
    
    for device_type in ['dds', 'ttl', 'dac']:
        devices = config_data.get(device_type, {})
        print(f"\n{device_type.upper()} DEVICES ({len(devices)} total):")
        print("-" * 40)
        
        for name, props in devices.items():
            if device_type == 'dds':
                print(f"  {name:25} | Freq: {props['frequency']:12.1f} Hz | "
                      f"Amp: {props['amplitude']:5.3f} | V_pd: {props['v_pd']:6.3f} V | "
                      f"SW: {props['sw_state']}")
            elif device_type == 'ttl':
                print(f"  {name:25} | Ch: {props['ch']:2d} | Type: {props['type']:3s} | "
                      f"TTL: {props['ttl_state']}")
            elif device_type == 'dac':
                print(f"  {name:25} | Ch: {props['ch']:2d} | "
                      f"Voltage: {props['voltage']:6.3f} V | Max: {props['max_voltage']:6.3f} V")

def main():
    """Main function to generate device state configuration."""
    print("Generating device state configuration from _id files...")
    print(f"K-exp root directory: {kexp_root}")
    
    # Generate configuration
    config_data = generate_device_config()
    
    if config_data is None:
        print("Failed to generate configuration data.")
        return 1
    
    # Print summary
    print_summary(config_data)
    
    # Save to file
    output_file = save_config_file(config_data)
    
    if output_file:
        print(f"\nTotal devices found:")
        print(f"  DDS: {len(config_data['dds'])}")
        print(f"  TTL: {len(config_data['ttl'])}")
        print(f"  DAC: {len(config_data['dac'])}")
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())