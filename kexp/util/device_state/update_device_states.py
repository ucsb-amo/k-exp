#!/usr/bin/env python3
"""
Script to update device state configuration file from live Base object.

This script reads the current state values from the device frames (.dac, .dds, .ttl)
of a kexp.base.Base object and updates the device_state_config.json file with the
current live values.

Usage:
    from kexp.util.device_state.update_state_from_base import update_state_from_base
    
    # In your experiment class that inherits from Base:
    update_state_from_base(self)
    
    # Or standalone:
    base_obj = SomeExperiment()  # Your experiment class
    update_state_from_base(base_obj)
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import numpy as np

# Add the k-exp package to the path
script_dir = Path(__file__).parent
kexp_root = Path(os.getenv('code')) / 'k-exp'
sys.path.insert(0, str(kexp_root))

# Import device classes for isinstance checks
try:
    from kexp.control.artiq.DDS import DDS
    from kexp.control.artiq.DAC_CH import DAC_CH
    from kexp.control.artiq.TTL import TTL, TTL_OUT, TTL_IN
    from kexp import Base
except ImportError as e:
    print(f"Error importing device classes: {e}")
    print("Make sure the kexp package is available in the Python path")
    sys.exit(1)

def ensure_json_serializable(value):
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(value, (np.integer, np.int32, np.int64)):
        return int(value)
    elif isinstance(value, (np.floating, np.float32, np.float64)):
        return float(value)
    elif isinstance(value, np.ndarray):
        return value.tolist()
    elif isinstance(value, (list, tuple)):
        return [ensure_json_serializable(item) for item in value]
    elif isinstance(value, dict):
        return {key: ensure_json_serializable(val) for key, val in value.items()}
    else:
        return value

def extract_live_dds_states(dds_frame) -> Dict[str, Dict[str, Any]]:
    """Extract current DDS device states from a live dds_frame object."""
    devices = {}
    
    # Look for attributes that are DDS objects
    for attr_name in dir(dds_frame):
        if attr_name.startswith('_'):
            continue
            
        attr_value = getattr(dds_frame, attr_name)
        
        # Check if it's a DDS object using isinstance
        if isinstance(attr_value, DDS):
            # Get current live values and ensure JSON serializable
            frequency = ensure_json_serializable(getattr(attr_value, 'frequency', 0.0))
            amplitude = ensure_json_serializable(getattr(attr_value, 'amplitude', 0.0))
            v_pd = ensure_json_serializable(getattr(attr_value, 'v_pd', 0.0))
            sw_state = ensure_json_serializable(getattr(attr_value, 'sw_state', 0))
            urukul_idx = ensure_json_serializable(getattr(attr_value, 'urukul_idx', 0))
            ch = ensure_json_serializable(getattr(attr_value, 'ch', 0))
            aom_order = ensure_json_serializable(getattr(attr_value, 'aom_order', 0))
            
            devices[attr_name] = {
                'frequency': float(frequency),
                'amplitude': float(amplitude),
                'v_pd': float(v_pd),
                'urukul_idx': int(urukul_idx),
                'ch': int(ch),
                'state': int(sw_state),  # Store as integer (0/1)
                'transition': str(getattr(attr_value, 'transition', 'None')),
                'aom_order': int(aom_order)
            }
    
    return devices

def extract_live_ttl_states(ttl_frame) -> Dict[str, Dict[str, Any]]:
    """Extract current TTL device states from a live ttl_frame object."""
    devices = {}
    
    # Look for attributes that are TTL objects
    for attr_name in dir(ttl_frame):
        if attr_name.startswith('_') or attr_name in ['ttl_list', 'camera']:
            continue
            
        attr_value = getattr(ttl_frame, attr_name)
        
        # Check if it's a TTL object using isinstance
        if isinstance(attr_value, TTL):
            # Determine the specific TTL type
            ttl_type = 'out'
            if isinstance(attr_value, TTL_IN):
                ttl_type = 'in'
            elif isinstance(attr_value, TTL_OUT):
                ttl_type = 'out'
            
            # Get actual state from the TTL object and ensure JSON serializable
            ttl_state = ensure_json_serializable(getattr(attr_value, 'state', 0))
            ch = ensure_json_serializable(getattr(attr_value, 'ch', 0))
            
            devices[attr_name] = {
                'ch': int(ch),
                'state': int(ttl_state),  # Store as integer (0/1)
                'type': str(ttl_type)
            }
    
    return devices

def extract_live_dac_states(dac_frame) -> Dict[str, Dict[str, Any]]:
    """Extract current DAC device states from a live dac_frame object."""
    devices = {}
    
    # Look for attributes that are DAC_CH objects
    for attr_name in dir(dac_frame):
        if attr_name.startswith('_') or attr_name in ['dac_device', 'dac_ch_list']:
            continue
            
        attr_value = getattr(dac_frame, attr_name)
        
        # Check if it's a DAC_CH object using isinstance
        if isinstance(attr_value, DAC_CH):
            # Get current live voltage value and ensure JSON serializable
            voltage = ensure_json_serializable(getattr(attr_value, 'v', 0.0))
            max_voltage = ensure_json_serializable(getattr(attr_value, 'max_v', 9.99))
            ch = ensure_json_serializable(getattr(attr_value, 'ch', 0))
            
            devices[attr_name] = {
                'ch': int(ch),
                'voltage': float(voltage),
                'max_voltage': float(max_voltage)
            }
    
    return devices

def load_existing_config(config_file: Path) -> Dict[str, Any]:
    """Load existing device configuration file."""
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading existing config file: {e}")
            return None
    else:
        print(f"Config file {config_file} does not exist. Creating new one.")
        return None

def save_updated_config(config_data: Dict[str, Any], config_file: Path) -> bool:
    """Save updated configuration data to file."""
    try:
        # Create directory if it doesn't exist
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Ensure all data is JSON serializable before saving
        serializable_config = ensure_json_serializable(config_data)
        
        with open(config_file, 'w') as f:
            json.dump(serializable_config, f, indent=2, sort_keys=True)
        print(f"Updated configuration saved to: {config_file}")
        return True
    except Exception as e:
        print(f"Error saving configuration file: {e}")
        print(f"Error details: {type(e).__name__}: {e}")
        return False

def update_state_from_base(base_obj, config_file: Optional[Path] = None, 
                          backup_existing: bool = True) -> bool:
    """
    Update device state configuration from a live Base object.
    
    Args:
        base_obj: Instance of kexp.base.Base (or subclass) with .dac, .dds, .ttl attributes
        config_file: Path to configuration file. If None, uses default location.
        backup_existing: Whether to create a backup of existing config file
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    # Verify the base object has the required attributes
    if not hasattr(base_obj, 'dac') or not hasattr(base_obj, 'dds') or not hasattr(base_obj, 'ttl'):
        print("Error: Base object must have .dac, .dds, and .ttl attributes")
        return False
    
    # Default config file location
    if config_file is None:
        config_file = script_dir / 'device_state_config.json'
    
    print(f"Updating device state configuration from live Base object...")
    print(f"Config file: {config_file}")
    
    # Load existing configuration
    existing_config = load_existing_config(config_file)
    
    # Create backup if requested and file exists
    if backup_existing and config_file.exists():
        backup_file = config_file.with_suffix('.json.backup')
        try:
            import shutil
            shutil.copy2(config_file, backup_file)
            print(f"Backup created: {backup_file}")
        except Exception as e:
            print(f"Warning: Could not create backup: {e}")
    
    # Extract current device states
    print("Extracting current device states...")
    
    try:
        dds_devices = extract_live_dds_states(base_obj.dds)
        print(f"  Found {len(dds_devices)} DDS devices")
    except Exception as e:
        print(f"  Error extracting DDS devices: {e}")
        dds_devices = {}
    
    try:
        ttl_devices = extract_live_ttl_states(base_obj.ttl)
        print(f"  Found {len(ttl_devices)} TTL devices")
    except Exception as e:
        print(f"  Error extracting TTL devices: {e}")
        ttl_devices = {}
    
    try:
        dac_devices = extract_live_dac_states(base_obj.dac)
        print(f"  Found {len(dac_devices)} DAC devices")
    except Exception as e:
        print(f"  Error extracting DAC devices: {e}")
        dac_devices = {}
    
    # Create updated configuration
    updated_config = {
        'dds': dds_devices,
        'ttl': ttl_devices,
        'dac': dac_devices,
        'metadata': {
            'updated_from': 'live_base_object',
            'timestamp': datetime.now().isoformat(),
            'previous_timestamp': existing_config.get('metadata', {}).get('timestamp', None) if existing_config else None,
            'total_devices_updated': len(dds_devices) + len(ttl_devices) + len(dac_devices)
        }
    }
    
    # Preserve any additional metadata from existing config
    if existing_config and 'metadata' in existing_config:
        for key, value in existing_config['metadata'].items():
            if key not in updated_config['metadata']:
                updated_config['metadata'][key] = value
    
    # Save updated configuration
    success = save_updated_config(updated_config, config_file)
    
    if success:
        print(f"\nSuccessfully updated device states:")
        print(f"  DDS devices: {len(dds_devices)}")
        print(f"  TTL devices: {len(ttl_devices)}")
        print(f"  DAC devices: {len(dac_devices)}")
        print(f"  Total: {len(dds_devices) + len(ttl_devices) + len(dac_devices)} devices")
    
    return success

def main():
    """Main function for standalone usage."""
    print("This script is designed to be imported and used with a live Base object.")
    print("Usage:")
    print("  from kexp.util.device_state.update_state_from_base import update_state_from_base")
    print("  update_state_from_base(your_base_object)")
    print("")
    print("For testing purposes, you would need to instantiate a Base object first.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())