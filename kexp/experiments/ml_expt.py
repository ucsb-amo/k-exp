
from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                    camera_select=cameras.xy_basler,
                    imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 9000.e-6
        # self.xvar('t_tof',np.linspace(30.,800.,10)*1.e-6)


        self.p.detune_d2_c_mot = -0.3270312283086232
        self.p.detune_d2_r_mot = -5.112520510695003
        self.p.i_mot = 20.90449450427454
        self.p.v_zshim_current = 0.460397405678056
        self.p.v_xshim_current = 0.8386280869221068
        self.p.v_yshim_current = 4.183319756464202
        self.p.detune_d1_c_d1cmot = 7.1353078435120985
        self.p.detune_d2_r_d1cmot = -2.768321992538147
        self.p.pfrac_d1_c_d1cmot = 0.8744686279456564
        self.p.amp_d2_r_d1cmot = 0.17067534203590845
        self.p.v_zshim_current_gm = 0.2759460934295864
        self.p.v_xshim_current_gm = 3.618017880735826
        self.p.v_yshim_current_gm = 4.403907722480723
        self.p.pfrac_d1_c_gm = 0.7626718160310394
        self.p.pfrac_d1_r_gm = 0.4261476304668388
        self.p.pfrac_c_gmramp_end = 0.7233073339087661
        self.p.pfrac_r_gmramp_end = 0.7776491466362678
        self.p.i_magtrap_init = 66.87512041698928

        self.p.t_magtrap_hold = .15

        self.p.imaging_state = 2.

        self.p.amp_imaging = .5

        self.p.N_repeats = 1
        self.p.t_mot_load = .5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.imaging.set_power(power_control_parameter=self.p.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,
                            do_magtrap_rampup=False,
                            do_magtrap_hold=False,
                            do_magtrap_rampdown=False)
        delay(self.p.t_magtrap_hold)
        self.inner_coil.snap_off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

