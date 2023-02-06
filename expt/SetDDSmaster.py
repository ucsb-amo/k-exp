from artiq.experiment import *
from DDS import DDS

class SetDDSmaster(EnvExperiment):

    def specify_dds_settings(self, DDS_list):
        '''For now, DDS frequencies must be set in Hz (weird float error)'''

        DDS_list[0][0] = DDS(urukul_idx=0, ch=0, freq_Hz=0, att_dB=0)
        DDS_list[1][3] = DDS(1,3,100000000,0)

        return DDS_list

    def prep_default_DDS_list(self):
        ''' Preps a list of DDS states, defaulting to off. '''

        DDS_list = [[None]*4]*3
        for urukul_idx in range(3):
            for ch in range(4):
                DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,0,0)
        return DDS_list

    def get_dds(self,dds):
        '''Fetch a DDS device from its name in device-db.py'''

        self.setattr_device(dds.name())
        dds.dds_device = self.get_device(dds.name())
        return dds

    @kernel
    def set_dds(self,dds):
        '''Set a dds device. If freq_Hz = 0, turn it off'''

        dds.dds_device.cpld.init()
        dds.dds_device.init()

        if dds.freq_Hz != 0:
            dds.dds_device.set(dds.freq_Hz * Hz, amplitude = 1.)
            dds.dds_device.set_att(dds.att_dB * dB)
            dds.dds_device.sw.on()
        else:
            dds.dds_device.sw.off()
            dds.dds_device.power_down()

    def build(self):
        '''Prep lists, set parameters manually, get the device drivers.'''

        self.setattr_device("core")
        self.DDS_list = self.prep_default_DDS_list()
        self.DDS_list = self.specify_dds_settings(self.DDS_list)
        self.DDS_list = [[self.get_dds(dds) for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]
    
    @kernel
    def run(self):
        '''Execute on the core device, set the DDS devices to the corresponding parameters'''

        self.core.reset()
        [[self.set_dds(dds) for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]

        