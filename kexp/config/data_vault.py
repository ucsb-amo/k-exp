import numpy as np
from waxx.config.data_vault import DataVault as DataVaultWax

class DataVault(DataVaultWax):
    def __init__(self, expt):
        super().__init__(expt)
        
        self.apd = self.add_data_container(1, np.float64)

        self.b = self.add_data_container(1)