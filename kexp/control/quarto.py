from kexp.control.artiq.TTL import TTL
import serial

BAUDRATE = 9600

class Quarto_Triggered_Ramp():
    def __init__(self,output_ch:int,trigger_ttl:TTL,COM):
        self.output_ch = output_ch
        self.ttl = trigger_ttl
        self.COM = COM
        self.conn = serial.Serial(port=self.COM,baudrate=BAUDRATE,bytesize=8, timeout=2)

    def update_linear_ramp(self,vi,vf,N,t):
        