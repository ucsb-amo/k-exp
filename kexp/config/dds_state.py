
from kexp.control.artiq.DDS import DDS
from artiq.experiment import *

dds_state = [[
    DDS(0,0,98.00*MHz,0.1880),
    DDS(0,1,98.00*MHz,0.1880),
    DDS(0,2,125.40*MHz,0.1880),
    DDS(0,3,98.00*MHz,0.1880)],[
    DDS(1,0,125.40*MHz,0.1880),
    DDS(1,1,115.00*MHz,0.1130),
    DDS(1,2,104.92*MHz,0.1300),
    DDS(1,3,125.92*MHz,0.1300)]]
