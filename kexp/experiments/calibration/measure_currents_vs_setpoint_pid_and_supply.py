from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np
import vxi11
import csv
import os
from kexp.calibrations.magnets import compute_pid_overhead

# Keithely should be set up to measure 60A/V transducer (or change trandsucer
# factor here)

# Analyze in k-jam\analysis\measurements\current_vs_setpoint_pid_and_supply.ipynb

TRANSDUCER_A_PER_V = 60
PID_TRANSDUCER_A_PER_V = 40

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
        fname = 'i_current_vs_setpoint_pid_and_supply.csv'
        self.fpath = os.path.join(data_dir,fname)

        self.N = 100

        self.v_setpoint = np.linspace(0.1,3.5,self.N)

        self.v_transducer = np.zeros(self.v_setpoint.shape[0] * 2)

        self.v_transducer_pid = np.zeros(self.v_setpoint.shape[0])
        self.v_transducer_supply = np.zeros(self.v_setpoint.shape[0])

        self.multimeter = KeithleyDMM6500(self.v_transducer)

        self.finish_prepare()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, dds_off=False, dds_set=False)

        self.outer_coil.i_control_dac.set(0.)
        self.outer_coil.on()
        self.outer_coil.set_voltage(20.)

        for i in range(self.N):

            self.outer_coil.i_control_dac.set(self.v_setpoint[i])
            delay(200.e-3)

            self.core.wait_until_mu(now_mu())
            self.multimeter.read_voltage(i)
            delay(100.e-3)

        for i in range(self.N):

            v_set = self.v_setpoint[i]
            i_pid_approx = PID_TRANSDUCER_A_PER_V * v_set
            self.outer_coil.set_supply(i_pid_approx + compute_pid_overhead(i_pid_approx))
            delay(30.e-3)
            self.outer_coil.pid_dac.set(v_set)
            self.outer_coil.pid_ttl.on()
            delay(300.e-3)

            self.core.wait_until_mu(now_mu())
            self.multimeter.read_voltage(i + self.N)
            delay(100.e-3)
            self.outer_coil.pid_ttl.off()

        self.outer_coil.off()

    def write_csv_data(self):

        self.v_transducer_pid = self.multimeter.v_data[self.N:]
        self.i_transducer_pid = self.v_transducer_pid * TRANSDUCER_A_PER_V

        self.v_transducer_supply = self.multimeter.v_data[0:self.N]
        self.i_transducer_supply = self.v_transducer_supply * TRANSDUCER_A_PER_V

        with open(self.fpath, mode="w", newline="") as file:
            writer = csv.writer(file)
            
            # Writing the header
            writer.writerow(["v_setpoint (A)", "v_transducer_pid (V)", "i_transducer_pid (A)",
                             "v_transducer_supply (A)", "i_transducer_supply (A)"])
            
            # Writing the data
            for row in zip(self.v_setpoint,
                            self.v_transducer_pid, self.i_transducer_pid,
                            self.v_transducer_supply, self.i_transducer_supply):
                writer.writerow(row)

            print(f"Data successfully written to {self.fpath}")

    def analyze(self):
        import os

        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        self.write_csv_data()