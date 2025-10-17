#!/usr/bin/env python3
"""
Simple launcher script for the Ethernet Relay GUI.
This script can be run directly from the command line.
"""

import sys
import os

# Add the current directory to the Python path so we can import ethernet_relay
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Now import and run the GUI
from ethernet_relay_gui import main

if __name__ == "__main__":
    main()
