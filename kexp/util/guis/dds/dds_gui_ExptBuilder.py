import os
import textwrap
from subprocess import PIPE, run
from kexp.control.artiq.DDS import DDS

class DDSGUIExptBuilder():

    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__,"k-exp","kexp","experiments","dds_gui_expt.py")

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode

    def make_all_dds_on_expt(self,dds_setting_lines):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp.control.artiq.DDS import DDS
        from kexp.config.dds_id import dds_empty_frame
        from kexp import Base

        class set_all_dds_on(EnvExperiment):

            def specify_dds_settings(self):
                {dds_setting_lines}

            def dds(self,urukul_idx,ch,frequency,amplitude):
                
                self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,frequency,amplitude)

            def prep_default_DDS_list(self):
                ''' Preps a list of DDS states, defaulting to off. '''

                self.DDS_list = dds_empty_frame()

                for urukul_idx in range(len(self.DDS_list)):
                    for ch in range(len(self.DDS_list[urukul_idx])):
                        self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,frequency=0.,amplitude=0.)

            def get_dds(self,dds):
                '''Fetch a DDS device from its name in device-db.py'''

                dds.dds_device = self.get_device(dds.name)
                return dds

            @kernel
            def set_all_dds(self):
                for dds_sublist in self.DDS_list:
                    for dds in dds_sublist:
                        dds.dds_device.init()
                        delay(1*ms)
                        dds.dds_device.set(frequency=dds.frequency,amplitude=dds.amplitude)
                        delay(1*us)
                        dds.on()

            @kernel
            def init_all_cpld(self):
                for dds_sublist in self.DDS_list:
                    for dds in dds_sublist:
                        dds.dds_device.cpld.init()
                        delay(1*ms)

            def build(self):
                '''Prep lists, set parameters manually, get the device drivers.'''

                self.setattr_device("core")
                self.prep_default_DDS_list()
                self.specify_dds_settings()
                self.DDS_list = [[self.get_dds(dds) for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]

            @kernel
            def run(self):
                '''Execute on the core device, init then set the DDS devices to the corresponding parameters'''

                self.core.reset()
                self.init_all_cpld()
                self.core.break_realtime()
                self.set_all_dds()
        """)
        return script
    
    def make_all_dds_off_expt(self):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp.control.artiq.DDS import DDS
        from kexp.config.dds_id import dds_empty_frame

        class set_all_dds_off(EnvExperiment):

            def list_dds(self,urukul_idx,ch,frequency,amplitude):
                self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,frequency,amplitude)

            def prep_default_DDS_list(self):
                ''' Preps a list of DDS states, defaulting to off. '''
                self.DDS_list = dds_empty_frame()

                for urukul_idx in range(len(self.DDS_list)):
                    for ch in range(len(self.DDS_list[urukul_idx])):
                        self.list_dds(urukul_idx,ch,frequency=0.,amplitude=0.)

            def get_dds(self,dds):
                '''Fetch a DDS device from its name in device-db.py'''
                dds.dds_device = self.get_device(dds.name)
                return dds

            @kernel
            def set_all_dds(self):
                for dds_sublist in self.DDS_list:
                    for dds in dds_sublist:
                        dds.dds_device.init()
                        delay(1*ms)
                        dds.off()
                        delay(1*us)

            @kernel
            def init_all_cpld(self):
                for dds_sublist in self.DDS_list:
                    for dds in dds_sublist:
                        dds.dds_device.cpld.init()
                        delay(1*ms)

            def build(self):
                '''Prep lists, set parameters manually, get the device drivers.'''
                self.setattr_device("core")
                self.prep_default_DDS_list()
                self.DDS_list = [[self.get_dds(dds) for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]

            @kernel
            def run(self):
                self.core.reset()
                self.init_all_cpld()
                self.core.break_realtime()
                self.set_all_dds()
        """)
        return script
    
    def make_single_dds_on_expt(self,dds_to_turn_on):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp.control.artiq.DDS import DDS

        class set_single_dds_on(EnvExperiment):

            def build(self):
                '''Prep lists, set parameters manually, get the device drivers.'''

                self.setattr_device("core")
                self.dds_device = self.get_device('{dds_to_turn_on.name}')

            @kernel
            def run(self):
                '''Execute on the core device, init then set the DDS devices to the corresponding parameters'''

                self.core.reset()
                self.dds_device.cpld.init()
                delay(1*ms)
                self.dds_device.init()
                delay_mu(8)
                self.dds_device.set(frequency={dds_to_turn_on.frequency}, amplitude={dds_to_turn_on.amplitude})
                self.dds_device.sw.on()
        """)
        return script
    
    def make_single_dds_off_expt(self,dds_to_turn_off):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp.control.artiq.DDS import DDS

        class set_single_dds_off(EnvExperiment):

            def build(self):
                '''Prep lists, set parameters manually, get the device drivers.'''

                self.setattr_device("core")
                self.dds_device = self.get_device('{dds_to_turn_off.name}')

            @kernel
            def run(self):
                '''Execute on the core device, init then set the DDS devices to the corresponding parameters'''

                self.core.reset()
                self.dds_device.init()
                delay_mu(8)
                self.dds_device.sw.off()
        """)
        return script

    def make_dds_setting_lines(self,dds_list):

        dds_setting_lines = ""

        for dds_slist in dds_list:
            for dds in dds_slist:

                uru_idx = dds.urukul_idx
                ch = dds.ch
                freq = dds.frequency
                amplitude = dds.amplitude

                dds_setting_lines += f"""
                    self.dds({uru_idx},{ch},{freq},{amplitude})"""

        return dds_setting_lines
    
    def write_experiment_to_file(self,program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def execute_set_from_gui(self,dds_list):
        dds_setting_lines = self.make_dds_setting_lines(dds_list)
        program = self.make_all_dds_on_expt(dds_setting_lines)
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode
    
    def execute_all_dds_off(self):
        program = self.make_all_dds_off_expt()
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode

    def execute_single_dds_off(self,dds_to_turn_off):
        print(dds_to_turn_off.name)
        program = self.make_single_dds_off_expt(dds_to_turn_off)
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode
    
    def execute_single_dds_on(self,dds_to_turn_on):
        print(dds_to_turn_on.name)
        print(dds_to_turn_on.frequency)
        print(dds_to_turn_on.amplitude)
        program = self.make_single_dds_on_expt(dds_to_turn_on)
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode
    
    
    