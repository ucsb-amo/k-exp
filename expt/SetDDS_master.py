from artiq.experiment import *
from DDS import DDS

class SetDDSmaster(EnvExperiment):

    def prep_default_DDS_lists(self):

        DDS_param_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        DDS_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]

        for urukul_idx in range(3):
            for ch in range(4):
                DDS_param_list[urukul_idx][ch] = DDS(urukul_idx,ch,0,0)

        return DDS_param_list, DDS_list

    def get_dds(self,dds_params):
        

        return dds

    def get_dds_list(self, DDS_param_list, DDS_list):
        for uru_idx in range(3):
            for ch_idx in range(4):

                this_dds_param = DDS_param_list[uru_idx][ch_idx]
                self.setattr_device(this_dds_param.name())
                this_dds = self.get_device(this_dds_param.name())
                DDS_list[uru_idx][ch_idx] = this_dds
            
        return DDS_list

    @kernel
    def set_dds(self,dds,dds_params):

        dds.cpld.init()
        dds.init()

        if dds_params.freq_MHz != 0:
            dds.set(dds_params.freq_MHz * MHz, amplitude = 1.)
            dds.set_att(dds_params.att_dB * dB)
            dds.sw.on()
        else:
            dds.sw.off()
            dds.power_down()

    @kernel
    def set_dds_list(self, DDS_param_list, DDS_list):

        for uru_idx in range(3):
            for ch_idx in range(4):
                this_dds = DDS_list[uru_idx][ch_idx]
                this_dds_params = DDS_param_list[uru_idx][ch_idx]
                self.set_dds(this_dds,this_dds_params)

    def build(self):

        self.setattr_device("core")

        self.DDS_param_list, DDS_list = self.prep_default_DDS_lists()

        # DDS_param_list[0][0] = DDS(urukul_idx=0, ch=0, freq_MHz=125, att_dB=0)
        # DDS_param_list[0][1] = DDS(urukul_idx=0, ch=1, freq_MHz=98, att_dB=0)
        # DDS_param_list[1][3] = DDS(1,3,100,0)

        self.DDS_list = self.get_dds_list(self.DDS_param_list, DDS_list)
    
    @kernel
    def run(self):

        self.core.reset()
        self.set_dds_list(self.DDS_param_list, self.DDS_list)

        