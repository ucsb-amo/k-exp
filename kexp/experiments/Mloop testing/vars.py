import numpy as np

class ParamSpace():
    def __init__(self):
        self.var_names = ['detune_gm','i_cmot']
        self.var_space = [[5,15],[10,30]]