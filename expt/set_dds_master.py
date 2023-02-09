from artiq.experiment import *
from DDS import DDS

class set_dds_master(EnvExperiment):

    '''
    set_dds_master

    Sets all dds channels

    Run me in Terminal (Win key, type "Terminal", Enter) with:
    artiq_run --device-db %db% %code%/k-exp/expt/set_dds_master.py
    '''

    def dds(self,urukul_idx,ch,freq_MHz,att_dB):
        
        self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,freq_MHz,att_dB)
        

    def specify_dds_settings(self):
        '''
        Manually specify channel parameters. All numbers must be floats (end in a decimal)
        To specify the parameters for a dds channel, add a line: 
        dds(urukul_idx,ch,freq_MHz,att_dB)
        The DDS puts out +10dBm with no attenuation. Reduce this with att_dB > 0
        '''

        # DDS_list[0][0] = DDS(urukul_idx=0, ch=0, freq_MHz=0., att_dB=0.)
        self.dds(0,0,98.,14.5)
        self.dds(0,1,98.,14.5)
        self.dds(0,2,125.4,13.7)
        self.dds(0,3,98.,14.5)
        self.dds(1,0,125.4,13.7)
        self.dds(1,3,20.,13.7)

    def prep_default_DDS_list(self):
        ''' Preps a list of DDS states, defaulting to off. '''

        self.DDS_list = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]

        for urukul_idx in range(len(self.DDS_list)):
            for ch in range(len(self.DDS_list[urukul_idx])):
                self.DDS_list[urukul_idx][ch] = DDS(urukul_idx,ch,freq_MHz=0.,att_dB=0.)

    def get_dds(self,dds):
        '''Fetch a DDS device from its name in device-db.py'''

        dds.dds_device = self.get_device(dds.name())
        return dds

    def build(self):
        '''Prep lists, set parameters manually, get the device drivers.'''

        self.setattr_device("core")
        self.prep_default_DDS_list()
        self.specify_dds_settings()
        self.DDS_list = [[self.get_dds(dds) for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]

    @kernel
    def run(self):
        '''Execute on the core device, init then set the DDS devices to the corresponding parameters'''

        self.core.reset()
        [[dds.init_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]
        [[dds.set_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.DDS_list]

        