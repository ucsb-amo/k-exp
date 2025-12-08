from waxx.util.device_state.generate_state_file import Generator

from kexp.config.monitor_config import MONITOR_STATE_FILEPATH

from kexp.config.dds_id import dds_frame
from kexp.config.dac_id import dac_frame
from kexp.config.ttl_id import ttl_frame

gen = Generator(dds_frame=dds_frame(),
          ttl_frame=ttl_frame(),
          dac_frame=dac_frame(),
          state_file_path=MONITOR_STATE_FILEPATH)

gen.generate()