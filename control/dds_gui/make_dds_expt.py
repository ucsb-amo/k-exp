import os
import textwrap
from subprocess import PIPE, run

class ParamList():
        def __init__(self,uru_idx,ch,freq,att):
            self.uru_idx = uru_idx
            self.ch = ch
            self.freq = freq
            self.att = att

class ExptBuilder():

    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__,"k-exp","expt","temp.py")

    def make_dds_expt(self,dds_setting_lines):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from DDS import DDS

        class set_dds_gui(EnvExperiment):

            def specify_dds_settings(self):
                {dds_setting_lines}

            def dds(self,urukul_idx,ch,freq_MHz,att_dB):
                
                self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,freq_MHz,att_dB)

            def prep_default_DDS_list(self):
                ''' Preps a list of DDS states, defaulting to off. '''

                self.DDS_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]

                for urukul_idx in range(len(self.DDS_list)):
                    for ch in range(len(self.DDS_list[urukul_idx])):
                        self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,freq_MHz=0.,att_dB=0.)

            def get_dds(self,dds):
                '''Fetch a DDS device from its name in device-db.py'''

                dds.dds_device = self.get_device(dds.name())
                return dds

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
                [[dds.init_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]
                [[dds.set_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]
        """)

        return script

    def make_dds_setting_lines(self,param_list):

        dds_setting_lines = ""

        for param in param_list:

            uru_idx = param.uru_idx
            ch = param.ch
            freq = param.freq
            att = param.att

            dds_setting_lines += f"""
                self.dds({uru_idx},{ch},{freq:.2f},{att:.1f})"""

        return dds_setting_lines

    def build_experiment(self,param_list):

        dds_setting_lines = self.make_dds_setting_lines(param_list)

        program = self.make_dds_expt(dds_setting_lines)

        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run --device-db %db% " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        # print(result.returncode, result.stdout, result.stderr)

    def execute_expt(self,param_list):
        self.build_experiment(param_list)
        self.run_expt()