from waxx.base import Scanner

class Adjust(Scanner):
    def __init__(self):
        self.adjust('t_tof',min_val=20.e-6, max_val=20.e-3)

        self.adjust('i_mot', min_val=0., max_val=80.)

        self.adjust('detune_d1_c_gm', min_val=0., max_val=13.)
        self.adjust('detune_d1_r_gm', min_val=0., max_val=13.)

        self.adjust('pfrac_d1_c_gm', min_val=0., max_val=1.)
        self.adjust('pfrac_d1_r_gm', min_val=0., max_val=1.)

        self.adjust('pfrac_r_gmramp_end', min_val=0., max_val=self.p.pfrac_d1_r_gm)
        self.adjust('pfrac_c_gmramp_end', min_val=0., max_val=self.p.pfrac_d1_c_gm)

        self.adjust('t_gm', min_val = 0., max_val = 10.e-3)
        self.adjust('t_gmramp', min_val = 0., max_val = 10.e-3)

        self.adjust('v_xshim_current',min_val=0.,max_val=9.9)
        self.adjust('v_yshim_current',min_val=0.,max_val=9.9)
        self.adjust('v_zshim_current',min_val=0.,max_val=9.9)

        self.adjust('v_xshim_current_gm',min_val=0.,max_val=9.9)
        self.adjust('v_yshim_current_gm',min_val=0.,max_val=9.9)
        self.adjust('v_zshim_current_gm',min_val=0.,max_val=9.9)

        self.adjust('v_xshim_current_magtrap',min_val=0.,max_val=9.9)
        self.adjust('v_yshim_current_magtrap',min_val=0.,max_val=9.9)
        self.adjust('v_zshim_current_magtrap',min_val=0.,max_val=9.9)

        self.adjust('t_lightsheet_rampup',min_val=25.e-3,max_val=500.e-3)
        self.adjust('v_pd_hf_lightsheet_rampdown_end',min_val=0.5,max_val=6.)
        self.adjust('i_magtrap_init',min_val=30.,max_val=160.)
        self.adjust('t_magtrap',min_val=0.5,max_val=3.)
        self.adjust('t_feshbach_field_rampup',min_val=50.e-3,max_val=300.e-3)

        self.adjust('t_mot_load',min_val=0.1,max_val=3.)
        self.adjust('t_d1cmot',min_val=1.e-3, max_val=50.e-3)