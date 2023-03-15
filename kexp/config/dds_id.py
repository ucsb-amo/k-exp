from kexp.config.dds_state import dds_state
from kexp.control.artiq.DDS import DDS

N_uru = 2
N_ch = 4
shape = (N_uru,N_ch)
dds_empty_frame = [[None for _ in range(N_ch)] for _ in range(N_uru)]

class dds_frame():
    '''
    Associates each dds in the dds_state file with a variable to be referenced in
    artiq experiments. Also, records the AOM order so that AOM frequencies can be
    determined from detunings.
    '''
    def __init__(self, dds_state = dds_state):

        self._N_uru = N_uru
        self._N_ch = N_ch
        self._shape = shape

        self._dds_state = dds_state

        self._aom_order = dds_empty_frame
        self._aom_order[0][0] = 1
        self._aom_order[0][1] = 1
        self._aom_order[0][2] = -1
        self._aom_order[0][3] = 1
        self._aom_order[1][0] = -1
        self._aom_order[1][1] = 1
        self._aom_order[1][2] = 1
        self._aom_order[1][3] = -1

        self.push = self.dds_assign(0,0)
        self.d2_2d_r = self.dds_assign(0,1)
        self.d2_2d_c = self.dds_assign(0,2)
        self.d2_3d_r = self.dds_assign(0,3)
        self.d2_3d_c = self.dds_assign(1,0)
        self.imaging = self.dds_assign(1,1)
        self.d1_3d_r = self.dds_assign(1,2)
        self.d1_3d_c = self.dds_assign(1,3)

    def dds_assign(self, uru, ch):
        dds0 = self._dds_state[uru][ch]
        dds0.aom_order = self._aom_order[uru][ch]
        return dds0
    
    def dds_list(self):
        '''
        Returns a list of all dds objects in 
        '''
        return [self.__dict__[key] for key in self.__dict__.keys() if isinstance(self.__dict__[key],DDS)]
    
    def get_dds_devices(self,expt):
        for dds in self.dds_list():
            dds.dds_device = expt.get_device(dds.name())
        

