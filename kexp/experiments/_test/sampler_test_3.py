from artiq.experiment import *                      #imports everything from experiment library
from artiq.coredevice.zotino import Zotino

#This code takes a single sample from all 8 sampler channels simultaneously 

class Sampler_Single_Sample(EnvExperiment):
    """Sampler Single Sample"""
    def prepare(self): #this code runs on the host device

        self.setattr_device("core")                 #saves core device drivers as attributes
        self.setattr_device("sampler0")             #saves sampler device drivers as attributes
        self.setattr_device("zotino0")
        
    @kernel #this code is run on the FPGA
    def run(self):
        self.core.reset()                           #resets core device
        
        self.core.break_realtime()                  #Time break to avoid underflow condition
        self.sampler0.init()                        #initialises sampler
        self.zotino0.init()

        self.zotino0.write_dac(30,1.)
        self.core.break_realtime()
        
        for i in range(8):                          #loops for each sampler channel
            self.sampler0.set_gain_mu(i, 0)         #sets each channel's gain to 0db
            delay(100*us)                           #100us delay
        
        n_channels = 8                              #sets number of channels to read off of
                                                    #change this number to alter the nummber of channels being read from
                                        
                                                    #channels are read from starting with the last one
                                                    #if you only use 1 channel, it is channel 7; 2 channels  will use 6 and 7

        delay(5*ms)                                 #5ms delay
 
        smp = [0.0]*n_channels                      #creates list of floating point variables 
                                                    #list is n_channels long
        self.core.break_realtime()
        self.sampler0.sample(smp)                   #runs sampler and saves to list
        self.core.break_realtime()
        for i in range(len(smp)):                   #loops over list of samples
            print(smp[i])                           #prints each item