import numpy as np
from waxa.data import DataVault as DataVaultWax

class DataVault(DataVaultWax):
    def __init__(self):
        super().__init__()
        
        self.apd = self.add_data_container('apd', 1, np.float64)