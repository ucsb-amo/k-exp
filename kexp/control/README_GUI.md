# Ethernet Relay GUI

A PyQt6-based graphical user interface for controlling the Ethernet Relay system.

## Features

- **Source Control**: Turn the source on/off with visual feedback
- **Status Indicator**: Real-time display of source status (ON/OFF)
- **ARTIQ Control**: Restart ARTIQ with confirmation dialog
- **Auto-refresh**: Status updates every 5 seconds
- **Error Handling**: Graceful error handling with user notifications

## Installation

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the GUI:
   ```bash
   python run_relay_gui.py
   ```
   
   Or run the GUI module directly:
   ```bash
   python ethernet_relay_gui.py
   ```

## GUI Components

### Source Control Group
- **Status Indicator**: Shows current source status with color coding:
  - Green (ON): Source is active
  - Red (OFF): Source is inactive
  - Yellow (CHECKING...): Status being updated
  - Purple (ERROR): Communication error
- **Turn Source ON**: Green button to activate the source
- **Turn Source OFF**: Red button to deactivate the source

### ARTIQ Control Group
- **Restart ARTIQ**: Orange button that prompts for confirmation before restarting ARTIQ

### Additional Controls
- **Refresh Status**: Manual status update button

## Safety Features

- **Confirmation Dialog**: ARTIQ restart requires user confirmation
- **Thread Safety**: Network operations run in background threads to prevent GUI freezing
- **Button Disabling**: Buttons are disabled during operations to prevent conflicts
- **Error Reporting**: Clear error messages for network or communication issues

## Configuration

The GUI uses the same configuration as the `ethernet_relay.py` module:
- `RELAY0_IP`: IP address of the relay controller
- `PORT`: Communication port
- `SOURCE_RELAY_IDX`: Relay index for the source
- `ARTIQ_RELAY_IDX`: Relay index for ARTIQ power

## Troubleshooting

1. **Import Errors**: Ensure both `ethernet_relay.py` and `ethernet_relay_gui.py` are in the same directory
2. **Network Errors**: Check that the relay controller is accessible at the configured IP address
3. **PyQt6 Issues**: Make sure PyQt6 is properly installed with `pip install PyQt6`
