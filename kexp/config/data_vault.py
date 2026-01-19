import numpy as np
from waxa.data import DataVault as DataVaultWax

class DataVault(DataVaultWax):
    def __init__(self, expt):
        super().__init__(expt)
        
        self.apd = self.add_data_container(1, np.float64)