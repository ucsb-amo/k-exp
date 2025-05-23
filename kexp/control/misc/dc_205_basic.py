import serial
import time



"""
Example Python code to communicate with a DC205 (or similar device)
at 115200 baud over serial, using pySerial.
"""
# Adjust the port name (e.g., 'COM3' on Windows, '/dev/ttyUSB0' or '/dev/ttyACM0' on Linux)
port_name = 'COM5'  
baud_rate = 115200

# Optional: specify timeouts or flow control if your device needs them.
# E.g.:
#   timeout=2 -> wait up to 2 seconds for a response,
#   write_timeout=2 -> wait up to 2 seconds for a write to complete.
#   Also set rtscts=True if hardware flow control is needed.

ser = serial.Serial(
    port=port_name,
    baudrate=baud_rate,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2,          # read timeout in seconds
    write_timeout=2
)

# Confirm the port is open
if ser.is_open:
    print(f"Serial port {port_name} opened at {baud_rate} baud.")
else:
    print(f"Failed to open {port_name}.")
    

# Give the device a moment to reset or be ready
time.sleep(1.0)

# Example command: perhaps DC205 needs some ASCII query like "*IDN?" or "READ?"
# Adjust to your device's protocol:
command = "*IDN?\n"   # For instruments that speak SCPI-like commands
# Another example might be "MEAS?\r" or something device-specific.

# Write the command
ser.write(command.encode('utf-8'))
print(f"Sent command: {command.strip()}")



# Read the response (if any)
response = ser.readline().decode('utf-8').strip()
print(f"Received response: {response}")

setRange = "RANGE10 1\r\n"
# Write the command
ser.write(setRange.encode('utf-8'))
print(f"Sent command: {setRange.strip()}")

rangeQuery = "RNGE?\n"
# Write the command
ser.write(rangeQuery.encode('utf-8'))
print(f"Sent command: {rangeQuery.strip()}")


# Read the response (if any)
response = ser.readline().decode('utf-8').strip()
print(f"Received response: {response}")



def voltageOut(v):
    rangeHigh = 10
    vSet = "VOLT 1.25e-3; VOLT?\n"
    ser.write(vSet.encode('utf-8'))
    print(f"Sent command: {vSet.strip()}")


    # Read the response (if any)
    response = ser.readline().decode('utf-8').strip()
    print(f"Received response: {response}")


def close():
    # Close the port
    ser.close()
    print("Serial port closed.")
    # except:
    #     print("Unexpected Error")    
    # except serial.SerialException as e:
    #     print(f"Serial error: {e}")
    # except Exception as e:
    #     print(f"Unexpected error: {e}")


voltageOut(3)   