import os
import textwrap
from subprocess import PIPE, run

class DACGUIExptBuilder():
    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__, "k-exp", "kexp", "experiments", "dac_gui_expt.py")

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & ar " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)

    def execute_set_all_dac_voltage(self, channels, voltages):
        with open(self.__temp_exp_path__, "w") as f:
            f.write(textwrap.dedent(f'''
                import sys
                from artiq.experiment import *

                class SetAllDACVoltages(EnvExperiment):
                    def build(self):
                        # Specify the DAC device you want to control
                        self.dac_device = self.get_device("zotino0")
                        self.core = self.get_device("core")

                        # Set the channels to program
                        self.channels = {channels}


                        # Set the desired voltages for each channel
                        self.voltages = {voltages}

                        # self.voltages0 = [1.0] * len(self.channels)


                    @kernel
                    def run(self):
                        self.core.reset()
                        self.dac_device.init()

                        self.core.break_realtime()

                        delay(20 * us)

                        # Program the DAC channels and pulse LDAC
                        self.dac_device.set_dac(self.voltages, channels=self.channels)
                        
                        # delay(3 * s)

                        # #self.core.break_realtime()

                        # Set the DAC register for the channels to 0
                        # self.dac_device.set_dac(self.voltages0, channels=self.channels)
            '''))

        self.run_expt()


#####CHDACGUIExptBuilder for HOPEFULLY 1 CH. only


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

    def make_dac_voltage_expt(self, channel, voltage):
        script = textwrap.dedent(f"""
        from artiq.experiment import *

        class SetDACVoltage(EnvExperiment):
            def build(self):
                self.dac_device = self.get_device("zotino0")
                self.core = self.get_device("core")

                self.channel = {channel}
                self.voltage = {voltage}

            @kernel
            def run(self):
                self.core.reset()
                self.dac_device.init()
                
                dac_value = self.dac_device.voltage_to_mu(self.voltage)

                self.dac_device.write_dac_mu(self.channel, dac_value)

                self.dac_device.load()

                # delay(3*s)

                # self.dac_device.write_dac(self.channel, 0.)

                # self.dac_device.load()
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