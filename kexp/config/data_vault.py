import numpy as np
from waxx.config.data_vault import DataVault as DataVaultWax, DataContainer

class DataVault(DataVaultWax):
    def __init__(self, expt):
        super().__init__(expt)
        
        self.apd = self.add_data_container(1, np.float64)

        self.post_shot_absorption = self.add_data_container(4)

        self.b = self.add_data_container(1)

        # Outer-coil current at the first camera trigger of each shot (A),
        # written once per shot by Image.record_imaging_conditions. Analysis
        # switches the absorption cross section on it
        # (waxa.calibrations.cross_section). Zero if the shot never imaged.
        self.i_outer_imaging = self.add_data_container(1)  # A

        self.frequency_wavemeter_405 = self.add_data_container(1)
        self.frequency_wavemeter_980 = self.add_data_container(1)
        self.frequency_siglent_405 = self.add_data_container(1)
        self.frequency_siglent_980 = self.add_data_container(1)

        # Raman laser frequency from the Bristol wavemeter server, read once
        # per shot at its start (Control.read_raman_wavemeter): the mean of
        # the last p.N_raman_wavemeter_avg readings no older than
        # p.t_raman_wavemeter_max_age, minus p.frequency_raman_wavemeter_reference
        # (Hz), and the sample std of those readings (Hz). Both 0. when no
        # reading was had that shot (server down/old, no fresh readings).
        self.frequency_detuned_raman = self.add_data_container(1)  # Hz
        self.frequency_raman_detuning_std = self.add_data_container(1)  # Hz