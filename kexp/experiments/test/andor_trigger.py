from kexp import Base, cameras, img_types
from artiq.experiment import *

class AndorPulse(EnvExperiment, Base):
	def prepare(self):
		Base.__init__(self,setup_camera=False)
		self.ttl.camera = self.ttl.andor
		self.camera_params = cameras.andor
		self.camera_params.select_imaging_type(img_types.ABSORPTION)
		self.camera_params.exposure_time = 10.e-6
		self.p.t_imaging_pulse = self.camera_params.exposure_time
		self.finish_prepare()

	@kernel
	def run(self):
		self.init_kernel()
		self.dds.imaging.set_dds(amplitude=0.5)
		self.ttl.imaging_shutter_x.on()
		self.light_image()