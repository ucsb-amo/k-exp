
from kexp.control.artiq.DDS import DDS
from artiq.experiment import *

dds_state = [[
    DDS(0,0,98.00*MHz,0.188),
    DDS(0,1,98.00*MHz,0.188),
    DDS(0,2,125.40*MHz,0.188),
    DDS(0,3,98.00*MHz,0.188)],[
    DDS(1,0,125.40*MHz,0.188),
    DDS(1,1,115.00*MHz,0.113),
    DDS(1,2,76.70*MHz,0.270),
    DDS(1,3,153.50*MHz,0.092)]]
