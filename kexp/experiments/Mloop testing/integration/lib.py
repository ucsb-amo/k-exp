class ExptBuilder():
    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__, "k-exp", "kexp", "experiments", "ml_expt.py")

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode
    
    def write_experiment_to_file(self, program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def execute_test(self, varname, var):
            program = self.test_expt(varname,var)
            self.write_experiment_to_file(program)
            #returncode = self.run_expt()
            return True

    # func. for generating exp, here GM TOF is copied in
    def test_expt(self, varname, var):
        script = textwrap.dedent(f"""
            from artiq.experiment import *
            from artiq.experiment import delay
            from kexp import Base
            import numpy as np                     
            class tof(EnvExperiment, Base):
                def build(self):
                    Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

                    self.p.imaging_state = 2.

                    #self.xvar('t_tof',np.linspace(230.,700.,10)*1.e-6)

                    self.p.t_tof = 450*1.e-6

                    self.xvar('{varname}', [{var}]*3)

                    self.p.t_mot_load = .5
                    

                    self.finish_build(shuffle=True)

                @kernel
                def scan_kernel(self):

                    self.dds.init_cooling()

                    self.switch_d2_2d(1)
                    self.mot(self.p.t_mot_load)
                    self.dds.push.off()
                    # self.cmot_d1(self.p.t_d1cmot)
                    # self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                    #                 v_yshim_current=self.p.v_yshim_current_gm,
                    #                   v_xshim_current=self.p.v_xshim_current_gm)

                    # self.gm(self.p.t_gm)
                    # self.gm_ramp(self.p.t_gmramp)

                    self.release()

                    delay(self.p.t_tof)
                    self.flash_repump()
                    self.abs_image()
                
                @kernel
                def run(self):
                    self.init_kernel()
                    self.load_2D_mot(self.p.t_2D_mot_load_delay)
                    self.scan()
                    self.mot_observe()

                def analyze(self):
                    import os
                    expt_filepath = os.path.abspath(__file__)
                    self.end(expt_filepath)

        """)
        return script

    # def execute_test(self, channel, duration):
    #         program = self.pulse_ttl_expt(channel, duration)
    #         self.write_experiment_to_file(program)
    #         returncode = self.run_expt()
    #         return returncode
