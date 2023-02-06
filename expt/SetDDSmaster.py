from artiq.experiment import *
from DDS import DDS

class SetDDSmaster(EnvExperiment):

    def specify_dds_settings(self, DDS_param_list):
        '''For now, DDS frequencies must be set in Hz (weird float error)'''
        DDS_param_list[0][0] = DDS(urukul_idx=0, ch=0, freq_Hz=0, att_dB=0)
        # self.DDS_param_list[0][1] = DDS(urukul_idx=0, ch=1, freq_Hz=98000000, att_dB=0)
        DDS_param_list[1][3] = DDS(1,3,0,0)

        return DDS_param_list

    def prep_default_DDS_lists(self):
        ''' Preps a list of DDS states, defaulting to off. Also get a same-size list to fill with DDS devices. '''
        DDS_param_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        DDS_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]

        for urukul_idx in range(3):
            for ch in range(4):
                DDS_param_list[urukul_idx][ch] = DDS(urukul_idx,ch,0,0)

        return DDS_param_list, DDS_list

    def get_dds(self,dds_param):
        '''Fetch a DDS device from its name in device-db.py'''
        self.setattr_device(dds_param.name())
        dds = self.get_device(dds_param.name())
        return dds

    def get_dds_list(self, DDS_param_list, DDS_list):
        '''Loop through the list of DDS names and store the device drivers in a list'''
        for uru_idx in range(3):
            for ch_idx in range(4):
                DDS_list[uru_idx][ch_idx] = self.get_dds(DDS_param_list[uru_idx][ch_idx])
        return DDS_list

    @kernel
    def set_dds(self,dds,dds_params):
        '''Set a dds device with dds_params. If freq_Hz = 0, turn it off'''

        dds.cpld.init()
        dds.init()

        if dds_params.freq_Hz != 0:
            dds.set(dds_params.freq_Hz * Hz, amplitude = 1.)
            dds.set_att(dds_params.att_dB * dB)
            dds.sw.on()
        else:
            dds.sw.off()
            dds.power_down()

    @kernel
    def set_dds_list(self, DDS_param_list, DDS_list):
        '''Set a list of dds devices to the corresponding parameters'''

        for uru_idx in range(3):
            for ch_idx in range(4):
                this_dds = DDS_list[uru_idx][ch_idx]
                this_dds_params = DDS_param_list[uru_idx][ch_idx]
                self.set_dds(this_dds,this_dds_params)

    def build(self):
        '''Prep lists, set parameters manually, get the devices, and set each dds.'''

        self.setattr_device("core")

        self.DDS_param_list, DDS_list = self.prep_default_DDS_lists()

        self.DDS_param_list = self.specify_dds_settings(self.DDS_param_list)

        self.DDS_list = self.get_dds_list(self.DDS_param_list, DDS_list)
    
    @kernel
    def run(self):
        '''Execute on the core device, set the DDS devices to the corresponding parameters'''

        self.core.reset()
        self.set_dds_list(self.DDS_param_list, self.DDS_list)

        