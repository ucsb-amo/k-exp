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
    
    # Look for attributes that are DDS objects (assigned via dds_assign)
    for attr_name in dir(frame_obj):
        if attr_name.startswith('_'):
            continue
            
        attr_value = getattr(frame_obj, attr_name)
        
        # Check if it's a DDS object using isinstance
        if isinstance(attr_value, DDS):
            sw_state = getattr(attr_value, 'sw_state', 0)
            devices[attr_name] = {
                'frequency': getattr(attr_value, 'frequency', 0.0),
                'amplitude': getattr(attr_value, 'amplitude', 0.0),
                'v_pd': getattr(attr_value, 'v_pd', 0.0),  # voltage photodiode setpoint
                'urukul_idx': getattr(attr_value, 'urukul_idx', 0),
                'ch': getattr(attr_value, 'ch', 0),
                'sw_state': sw_state,  # Hardware switch state (0/1)
                'transition': getattr(attr_value, 'transition', 'None'),
                'aom_order': getattr(attr_value, 'aom_order', 0)
            }
    
    return devices

def extract_ttl_devices(frame_obj) -> Dict[str, Dict[str, Any]]:
    """Extract TTL device states from a ttl_frame object."""
    devices = {}
    
    # Look for attributes that are TTL objects (assigned via assign_ttl_out/assign_ttl_in)
    for attr_name in dir(frame_obj):
        if attr_name.startswith('_') or attr_name in ['ttl_list', 'camera']:
            continue
            
        attr_value = getattr(frame_obj, attr_name)
        
        # Check if it's a TTL object using isinstance
        if isinstance(attr_value, TTL):
            # Determine the specific TTL type
            ttl_type = 'out'
            if isinstance(attr_value, TTL_IN):
                ttl_type = 'in'
            elif isinstance(attr_value, TTL_OUT):
                ttl_type = 'out'
            
            # Get actual state from the TTL object
            ttl_state = getattr(attr_value, 'state', 0)
            
            devices[attr_name] = {
                'ch': getattr(attr_value, 'ch', 0),
                'ttl_state': ttl_state,  # Raw state value (0/1)
                'type': ttl_type
            }
    
    return devices

def extract_dac_devices(frame_obj) -> Dict[str, Dict[str, Any]]:
    """Extract DAC device states from a dac_frame object."""
    devices = {}
    
    # Look for attributes that are DAC_CH objects (assigned via assign_dac_ch)
    for attr_name in dir(frame_obj):
        if attr_name.startswith('_') or attr_name in ['dac_device', 'dac_ch_list']:
            continue
            
        attr_value = getattr(frame_obj, attr_name)
        
        # Check if it's a DAC_CH object using isinstance
        if isinstance(attr_value, DAC_CH):
            devices[attr_name] = {
                'ch': getattr(attr_value, 'ch', 0),
                'voltage': getattr(attr_value, 'v', 0.0),
                'max_voltage': getattr(attr_value, 'max_v', 9.99)
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
    
    try:
        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent=2, sort_keys=True)
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