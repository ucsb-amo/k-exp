import serial
import time
import math

class dc_205():
    def __init__(self):
        self.port = 'COM16'
        self.baud = 115200
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,          # read timeout in seconds
            write_timeout=2
        )
        # Confirm the port is open
        if self.ser.is_open:
            print(f"Serial port {self.port} opened at {self.baud} baud.")
        else:
            print(f"Failed to open {self.port}.")
            time.sleep(0.05)

    def test_connect(self):
        command = "*IDN?\n"   # For instruments that speak SCPI-like commands
        # Another example might be "MEAS?\r" or something device-specific.

        # Write the command
        self.ser.write(command.encode('utf-8'))
        print(f"Sent command: {command.strip()}")



        # Read the response (if any)
        response = self.ser.readline().decode('utf-8').strip()
        print(f"Received response: {response}")

        turnOnCMD = f"SOUT 0\n"
        self.ser.write(turnOnCMD.encode('utf-8'))
        print(f"Sent command: {turnOnCMD.strip()}")

    #v = 0,10,100
    def set_range(self,v):
        #rangeHigh = 10
        n = int(math.log10(v))
        vSet = f"RNGE {n}; RNGE?\n"
        self.ser.write(vSet.encode('utf-8'))
        print(f"Sent command: {vSet.strip()}")

        # Read the response (if any)
        response = self.ser.readline().decode('utf-8').strip()
        print(f"Received response: {response}")

    def set_voltage(self,v):
        #rangeHigh = 10
        vSet = f"VOLT {v}; VOLT?\n"
        self.ser.write(vSet.encode('utf-8'))
        print(f"Sent command: {vSet.strip()}")

#        Read the response (if any)
        response = self.ser.readline().decode('utf-8').strip()
        print(f"Received response: {response}")

        turnOnCMD = f"SOUT 1; SOUT?\n"
        self.ser.write(turnOnCMD.encode('utf-8'))
        print(f"Sent command: {turnOnCMD.strip()}")

        response = self.ser.readline().decode('utf-8').strip()
        print(f"Received response: {response}")
                    