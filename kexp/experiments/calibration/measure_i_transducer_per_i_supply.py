from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np
import vxi11
import csv
import os

# Keithely should be set up to measure 60A/V transducer (or change trandsucer
# factor here)

# Analyze in k-jam\analysis\measurements\i_transducer_per_i_supply.ipynb

TRANSDUCER_A_PER_V = 60

class KeithleyDMM6500():
    def __init__(self,data_array=np.array([]),ip='192.168.1.96'):
        self.ip = ip
        self.device = vxi11.Instrument(self.ip)
        self.v_data = data_array
        
    def read_voltage(self,idx):
        self.device.write(":MEAS?")
        self.v_data[idx] = float(self.device.read())
        print(self.v_data[idx])

class high_field_magnetometry(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)

        data_dir = r'G:\Shared drives\Tweezers\Measurements'
        fname = 'i_transducer_vs_i_supply.csv'
        self.fpath = os.path.join(data_dir,fname)

        self.N = 25

        self.i_supply = np.linspace(10.,200.,self.N)
        self.v_pid = np.zeros(self.i_supply.shape)
        self.i_transducer = np.zeros(self.i_supply.shape)

        self.multimeter = KeithleyDMM6500(self.v_pid)

        self.finish_prepare()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)

        self.outer_coil.i_control_dac.set(0.)
        self.outer_coil.on()
        self.outer_coil.set_voltage(20.)

        for i in range(self.N):

            v = self.outer_coil.supply_current_to_dac_voltage(self.i_supply[i])
            self.outer_coil.i_control_dac.set(v)
            delay(200.e-3)

            self.core.wait_until_mu(now_mu())
            self.multimeter.read_voltage(i)
            delay(100.e-3)

        self.outer_coil.off()

    def write_csv_data(self):

        self.v_pid = self.multimeter.v_data
        self.i_transducer = self.v_pid * TRANSDUCER_A_PER_V

        with open(self.fpath, mode="w", newline="") as file:
            writer = csv.writer(file)
            
            # Writing the header
            writer.writerow(["i_supply (A)", "v_pid (V)", "i_transducer (A)"])
            
            # Writing the data
            for row in zip(self.i_supply, self.v_pid, self.i_transducer):
                writer.writerow(row)

            print(f"Data successfully written to {self.fpath}")

    def analyze(self):
        import os

        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        self.write_csv_data()