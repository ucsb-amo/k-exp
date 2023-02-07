from artiq.experiment import *
from DDS import DDS

class SetDDSmaster(EnvExperiment):

    '''
    Run me in Terminal (Win key, type "Terminal", Enter) with:
    artiq_run --device-db %db% %code%/k-exp/expt/SetDDSmaster.py
    '''

    def specify_dds_settings(self, DDS_list):
        '''
        Manually specify channel parameters. All numbers must be floats (end in a decimal)
        To add a DDS, add a line: 
        DDS[urukul_index][channel_idx] = DDS(urukul_idx,ch,freq_MHz,att_dB)
        The DDS puts out +10dBm with no attenuation. Reduce this with att_dB > 0
        '''

        # DDS_list[0][0] = DDS(urukul_idx=0, ch=0, freq_MHz=0., att_dB=0.)
        DDS_list[0][3] = DDS(0,3,98.,14.5)
        DDS_list[1][0] = DDS(1,0,125.4,13.7)

        return DDS_list

    def prep_default_DDS_list(self):
        ''' Preps a list of DDS states, defaulting to off. '''

        DDS_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]

        for urukul_idx in range(len(DDS_list)):
            for ch in range(len(DDS_list[urukul_idx])):
                DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,freq_MHz=0.,att_dB=0.)
                
        return DDS_list

    def get_dds(self,dds):
        '''Fetch a DDS device from its name in device-db.py'''
        
        dds.dds_device = self.get_device(dds.name())
        return dds

    @kernel
    def set_dds(self,dds):
        '''Set a dds device. If freq_MHz = 0, turn it off'''

        dds.dds_device.cpld.init()
        dds.dds_device.init()

        if dds.freq_MHz != 0.:
            dds.dds_device.set(dds.freq_MHz * MHz, amplitude = 1.)
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

        