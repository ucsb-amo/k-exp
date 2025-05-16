import os
import textwrap
from subprocess import PIPE, run
from kexp.control.artiq.DDS import DDS
import numpy as np
from kexp.config.dds_id import dds_frame

class DDSGUIExptBuilder():

    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__,"k-exp","kexp","experiments","dds_gui_expt.py")

    def write_experiment_to_file(self,program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & ar " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode
    
    def execute(self,script):
        self.write_experiment_to_file(script)
        returncode = self.run_expt()
        return returncode
    
    def startup(self,dds_channels):
        get_lines = []
        init_lines = []
        for ch in dds_channels:
            dds = ch.dds
            dds: DDS
            get_lines += f"""
        self.setattr_device("{dds.cpld_name}")
        self.setattr_device("{dds.name}")"""
            init_lines += f"""
        self.{dds.cpld_name}.init()
        self.{dds.name}.init()
        delay(1*ms)"""
        script = textwrap.dedent(f"""
                    from artiq.experiment import *
                    from kexp import Base
                    class StartUp(EnvExperiment,Base):
                        def build(self):
                            self.core = self.get_device("core")
                            self.dac = self.get_device("zotino0")
                            {get_lines}
                        @kernel
                        def run(self):
                            self.core.break_realtime()
                            {init_lines}
                    """)
        returncode = self.execute(script)
        return(returncode)

    def one_on(self, dds:DDS):
        dac_load_line = "" 
        dac_control_line = ""
        dds.update_dac_bool()
        print(dds.dac_control_bool, dds.dac_ch)
        if dds.dac_control_bool:
            # dac_load_line = f"""self.dac = self.get_device("{dds.dac_device}")"""
            dac_load_line = f"""self.dac = self.get_device("zotino0")"""
            dac_control_line = f"self.dac.set_dac([{dds.v_pd}],[{dds.dac_ch}])"
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        class StartUp(EnvExperiment):
            def build(self):
                self.core = self.get_device("core")
                self.dds = self.get_device("{dds.name}")
                {dac_load_line}
            @kernel
            def run(self):
                self.core.break_realtime()
                self.dds.set(frequency={dds.frequency},amplitude={dds.amplitude})
                {dac_control_line}
                self.dds.sw.on()
        """)
        print(script)
        returncode = self.execute(script)
        return(returncode)  

    def one_off(self,dds:DDS):
        dac_load_line = ""
        dac_control_line = ""
        if dds.dac_control_bool:
            # dac_load_line = f"""self.dac = self.get_device("{dds.dac_device}")"""
            dac_load_line = f"""self.dac = self.get_device("zotino0")"""
            dac_control_line = f"self.dac.set_dac([0.],[{dds.dac_ch}])"
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        class StartUp(EnvExperiment):
            def build(self):
                self.core = self.get_device("core")
                self.dds = self.get_device("{dds.name}")
                {dac_load_line}
            @kernel
            def run(self):
                self.core.break_realtime()
                self.dds.set(frequency={dds.frequency},amplitude=0.)
                {dac_control_line}
                self.dds.sw.off()
        """)
        returncode = self.execute(script)
        return(returncode)

    def all_off(self, dds_channels):
        dac_control_line = ""
        set_lines = []
        get_lines = []
        for ch in dds_channels:
            dds = ch.dds
            dds: DDS
            if dds.dac_control_bool:
                dac_control_line = f"self.dac.set_dac([0.],[{dds.dac_ch}])"
            get_lines += f"""
        self.setattr_device("{dds.name}")"""
            set_lines += f"""
        self.{dds.name}.set(frequency={dds.frequency},amplitude=0.)
        self.{dds.name}.sw.off()
        {dac_control_line}
        delay(1*ms)"""
            
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        class all_on(EnvExperiment): 
            def build(self):
                self.core = self.get_device("core")
                self.dac = self.get_device("zotino0")
                {get_lines}

            @kernel
            def run(self):
                self.core.break_realtime()
                {set_lines}
        """)
        returncode = self.execute(script)
        return(returncode)

    def all_on(self, dds_channels): 
        dac_control_line = ""
        set_lines = []
        get_lines = []
        for ch in dds_channels:
            dds = ch.dds
            dds: DDS
            if dds.dac_control_bool:
                dac_control_line = f"self.dac.set([{dds.v_pd}],[{dds.dac_ch}])"
            get_lines += f"""
        self.setattr_device({dds.name})"""
            set_lines += f"""
        self.{dds.name}.set(frequency={dds.frequency},amplitude={dds.amplitude})
        self.{dds.name}.sw.on()
        {dac_control_line}
        delay(1*ms)"""
            
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        class all_on(EnvExperiment): 
            def build(self):
                self.core = self.get_device("core")
                self.dac = self.get_device("zotino0")
                {get_lines}

            @kernel
            def run(self):
                self.core.break_realtime()
                {set_lines}
        """)
        returncode = self.execute(script)
        return(returncode)

    