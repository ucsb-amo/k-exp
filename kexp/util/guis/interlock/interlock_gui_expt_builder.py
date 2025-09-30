import serial 
import time
import re
import codecs
import csv
import os
import textwrap
from subprocess import PIPE, run


class CHDACGUIExptBuilder():
    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__, "k-exp", "kexp", "experiments", "dac_gui_expt.py")

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & ar " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode

    def make_dac_voltage_expt(self):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp import Base, img_types

        class SetDACVoltage(EnvExperiment, Base):
                                 
            def prepare(self):
                Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)
                                 
                self.xvar('beans',[0])
                                 
                self.finish_prepare(shuffle=True)
            
            @kernel
            def scan_kernel(self):
                                 
                self.outer_coil.set_voltage(0.)
                self.inner_coil.set_voltage(0.)
                self.dac.xshim_current_control.set(9.)
                                 
            @kernel
            def run(self):
                self.init_kernel(setup_awg=False,setup_slm=False)
                self.scan()


        """)
        return script

    def write_experiment_to_file(self, program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def execute_set_dac_voltage(self, channel, voltage):
        program = self.make_dac_voltage_expt(channel, voltage)
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode