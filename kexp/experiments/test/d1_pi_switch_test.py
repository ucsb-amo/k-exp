from kexp import Base
from artiq.experiment import *
from artiq.experiment import delay, kernel, parallel

class d1_pi_switch_test(EnvExperiment,Base):
    def build(self):
        Base.__init__(self,setup_camera=False)
        self.core_dma = self.get_device("core_dma")

    @kernel
    def run(self):
        self.init_kernel()

        

        dds = self.dds.d1_3d_r

        with self.core_dma.record("ramp"):
            N = 1000
            for i in range(N):
                self.zotino.write_dac(dds.dac_ch_vpd_setpoint,(N - i)/N + 0.25)
                self.zotino.load()
                delay(10*us)

        # self.zotino.write_dac(dds.dac_ch_vpd_setpoint,0.)
        # self.zotino.load()

        # delay(1*ms)

        # dds.on()

        ramp_handle = self.core_dma.get_handle("ramp")

        delay(1*s)

        self.zotino.write_dac(dds.dac_ch_vpd_setpoint,1.2)
        self.zotino.load()
        dds.on()
        delay(1*ms)
        self.core_dma.playback("ramp")
        # delay(1*ms)
        # self.zotino.write_dac(dds.dac_ch_vpd_setpoint,0.2)
        # self.zotino.load()
        # delay(1*ms)
        # self.zotino.write_dac(dds.dac_ch_vpd_setpoint,0.)
        # self.zotino.load()

        delay(1*ms)
        dds.off()