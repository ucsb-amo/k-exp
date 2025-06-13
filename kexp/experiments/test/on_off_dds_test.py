from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
from artiq.language.core import now_mu, at_mu
import numpy as np

class on_off_dds_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.t = np.zeros(1000,dtype=np.int64)
        self.t_idx = 0

        self.finish_prepare()

    @kernel
    def get_time(self):
        """Get the current time in microseconds."""
        self.t[self.t_idx] = now_mu()
        self.t_idx += 1

    @kernel
    def run(self):
        self.init_kernel()

        # Everywhere a function is called, I've labeled the change in the
        # position of the timeline cursor, which controls the timestamp for
        # which the next event will be scheduled.

        ### TTL changes are immediate -- do not move the timeline cursor
        # The following code does not produce any output from the hardware,
        # since the on and off are scheduled for the same time.
        self.ttl.pd_scope_trig.on() # t += 0
        self.ttl.pd_scope_trig.off() # t += 0
        
        ### Behavior of DDS.on and DDS.off

        # DDS.on and DDS.off behavior depends on what needs to change when the
        # DDS is toggled -- does it include a DAC channel or not?

        # for a non-DAC controlled DDS
        self.dds.raman_plus.on() # t += 0
        self.dds.raman_plus.off() # t += 0

        # for a DAC controlled DDS, the same code does produce a delay, since
        # time is needed to write the DAC register updates
        self.dds.d1_3d_c.on() # t += 824 mu (ns) -- due to DAC set time
        self.dds.d1_3d_c.off() # t += 824 mu

        # for a DAC controlled DDS (where the DAC controls a VVA), you can
        # choose to not update the DAC register (i.e., only the RF switch will
        # be toggled)
        #
        # watch out -- DAC is by default set to 0V with DDS.off(), so if you
        # don't update the DAC, the RF amplitude to the AO will be 0V
        self.dds.d1_3d_c.on(dac_update=False) # t += 0
        self.dds.d1_3d_c.off(dac_update=False) # t += 0

        # for a DAC controlled DDS, you can also choose to just omit the LDAC
        # pulse, which is the TTL that tells the DAC to update from a new
        # register value. This is nice if you are trying to change many DAC
        # outputs at once, since this way you can have them all change
        # simultaneously.
        #
        # Here I left in `dac_update=True`, but this is the default behavior.
        # Note also that with `dac_update=False`, LDAC is not pulsed.
        self.dds.d1_3d_c.on(dac_update=True, dac_load=False) # t += 808 mu
        self.dds.d1_3d_c.off(dac_update=True, dac_load=False) # t += 808 mu

        # you can then pulse the LDAC manually. It is shared between all DAC channels,
        # so it doesn't matter how you access it.
        self.dds.d1_3d_c.dac_device.load() # t += 16 mu
        # or
        self.dac.load() # t += 16 mu
        # or through any other DAC controlled DDS:
        self.dds.d1_3d_r.dac_device.load() # t += 16 mu

        # Setting a DDS has an associated delay to write the register
        self.dds.raman_plus.set_dds(frequency=140.e6, amplitude=0.2) # t += 1256 mu (ns)

        # A DDS with a DAC controlled VVA will have an additional delay due to
        # the DAC write IF the DAC is updated to a new value.
        self.dds.d1_3d_c.set_dds(frequency=150.e6,
                                  amplitude=0.2,
                                  v_pd=1.) # t += 2080 mu (ns)

        # If the DDS is updated to parameters that it is already set to (as kept
        # track of in the DDS object), then no update takes place and so the
        # timeline cursor does not move.
        self.dds.d1_3d_c.set_dds(frequency=150.e6,
                                  amplitude=0.2) # t += 0
        self.dds.d1_3d_c.set_dds(frequency=150.e6,
                                  amplitude=0.2,
                                  v_pd=1.) # t += 0
        
        # If no change is made to frequency or amplitude, but the DAC changes,
        # the delay is just the DAC write time.
        self.dds.d1_3d_c.set_dds(frequency=150.e6,
                                  amplitude=0.2,
                                  v_pd=2.) # t += 824 mu

        # If you don't update the DAC setpoint (v_pd), the delay is just the DDS
        # register write
        self.dds.d1_3d_c.set_dds(frequency=140.e6, amplitude=0.5) # t += 1256 mu (ns)

        delay(1.e-3)


    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        # Find the index where t stops changing
        # Find the index where t stops changing for at least 10 consecutive elements
        diffs = np.diff(self.t)
        zero_runs = np.where(diffs == 0)[0]
        n = len(self.t)
        if len(zero_runs) >= 10:
            for i in range(len(zero_runs) - 9):
                if np.all(zero_runs[i:i+10] == np.arange(zero_runs[i], zero_runs[i]+10)):
                    n = zero_runs[i] + 1
                    break
        print(np.diff(self.t[:n-1]))
        self.end(expt_filepath)