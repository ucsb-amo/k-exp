from artiq.experiment import *
from DDS import DDS

class SetDDSmaster(EnvExperiment):

    @kernel
    def set_dds(self,dds,dds_params):

        dds.cpld.init()
        dds.init()

        if dds_params.freq_MHz > 0:
            dds.set(dds_params.freq_MHz * MHz, amplitude = 1.)
            dds.set_att(dds_params.att_dB * dB)
            dds.sw.on()
        else:
            dds.sw.off()
            dds.power_down()

    # def init_dds(self,dds_params):
    #     self.setattr_device(dds_params.name())
    #     dds = self.get_device(dds_params.name())

    #     dds.cpld.init()
    #     dds.init()

    #     return dds

    def build(self):

        self.setattr_device("core")

        n = 1
        empty_list = [[0]*n]*n
        DDS_param_list = empty_list
        DDS_list = empty_list

        for urukul_idx in range(n):
            for ch in range(n):
                DDS_param_list[urukul_idx][ch] = DDS(urukul_idx,ch,0,0)

        # DDS_param_list[0][0] = DDS(urukul_idx=0, ch=0, freq_MHz=125.4, att_dB=0)
        # DDS_param_list[0][1] = DDS(urukul_idx=0, ch=1, freq_MHz=98, att_dB=0)
        # DDS_param_list[1][3] = DDS(1,3,0,0)

        for uru_idx in range(len(DDS_param_list)):

            this_uru_dds_params = DDS_param_list[uru_idx]

            for ch_idx in range(len(this_uru_dds_params)):

                this_dds_param = DDS_param_list[uru_idx][ch_idx]

                self.setattr_device(this_dds_param.name())
                this_dds = self.get_device(this_dds_param.name())

                DDS_list[uru_idx][ch_idx] = this_dds
        
        self.DDS_param_list = DDS_param_list
        self.DDS_list = DDS_list
    
    @kernel
    def run(self):

        self.core.reset()

        for uru_idx in range(len(self.DDS_param_list)):

            for ch_idx in range(len(self.DDS_param_list[uru_idx])):

                this_dds = self.DDS_list[uru_idx][ch_idx]
                this_dds_params = self.DDS_param_list[uru_idx][ch_idx]
                self.set_dds(this_dds,this_dds_params)

        