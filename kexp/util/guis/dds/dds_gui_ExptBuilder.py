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
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode
    
    def execute(self,script):
        self.write_experiment_to_file(script)
        returncode = self.run_expt()
        return returncode
    
    def startup(self):
        script = textwrap.dedent(f"""
                    from artiq.experiment import *
                    from kexp import Base
                    class StartUp(EnvExperiment,Base):
                        def build(self):
                            Base.__init__(self,setup_camera=False)
                        @kernel
                        def run(self):
                            self.init_kernel()
                    """)
        returncode = self.execute(script)
        return(returncode)

    def one_on(self, dds):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp import Base
        class StartUp(EnvExperiment,Base):
            def build(self):
                Base.__init__(self,setup_camera=False)
            @kernel
            def run(self):
                self.init_kernel(init_dds=False,dds_set=False,dds_off=False)
                self.dds.dds_array[{dds.urukul_idx}][{dds.ch}].set_dds(frequency={dds.frequency},amplitude={dds.amplitude},v_pd={dds.v_pd})
                self.dds.dds_array[{dds.urukul_idx}][{dds.ch}].on()
        """)
        returncode = self.execute(script)
        return(returncode)   

    def one_off(self,dds):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp import Base
        class StartUp(EnvExperiment,Base):
            def build(self):
                Base.__init__(self,setup_camera=False)
            @kernel
            def run(self):
                self.init_kernel(init_dds=False,dds_set=False,dds_off=False)
                self.dds.dds_array[{dds.urukul_idx}][{dds.ch}].off()
        """)
        returncode = self.execute(script)
        return(returncode)

    def all_off(self):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp import Base
        def build(self):
            Base.__init__(self,setup_camera=False)
        @kernel
        def run(self):
            self.init_kernel(init_dds=False,dds_set=False,dds_off=False)
            for dds in self.dds.dds_list:
                dds.off()
                delay(1*ms)
        """)
        returncode = self.execute(script)
        return(returncode)

    def all_on(self, dds_channels):
        lines = []
        for ch in dds_channels:
            dds = ch.dds
            lines += f"""
        self.dds.dds_array[{dds.urukul_idx}][{dds.ch}].set_dds(frequency={dds.frequency},amplitude={dds.amplitude},v_pd={dds.v_pd})
        self.dds.dds_array[{dds.urukul_idx}][{dds.ch}].on()
        delay(1*ms)"""

        script = textwrap.dedent(f"""
        from artiq.experiment import *
        from kexp import Base
        def build(self):
            Base.__init__(self,setup_camera=False)
        @kernel
        def run(self):
            self.init_kernel(init_dds=False,dds_set=False,dds_off=False)
            {lines}
        """)
        returncode = self.execute(script)
        return(returncode)

        ############# here ends test.py written by JEP

    