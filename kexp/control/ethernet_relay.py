import time

from waxx.control.ethernet_relay import EthernetRelay as EthernetRelayWaxx

from kexp.config.ip import ETHERNET_RELAY_IP, ETHERNET_RELAY_PORT

N_RELAYS = 4

ARTIQ_MAIN_RELAY_IDX = 1
MAGNET_INHIBIT_IDX = 2
SOURCE_RELAY_IDX = 3
ARTIQ_SATELLITES_RELAY_IDX = 4

ARTIQ_RESTART_TIME_S = 3.
ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S = 5.

class EthernetRelay(EthernetRelayWaxx):
	def __init__(self):
		super().__init__(relay_ip=ETHERNET_RELAY_IP, port=ETHERNET_RELAY_PORT)
		
	def read_source_status(self):
		self.connect()
		out = bool(self.__board.get_relay_status_by_index(SOURCE_RELAY_IDX)[0])
		self.close()
		return out
	
	def source_off(self):
		self.connect()
		_ = self.__board.turn_off_relay_by_index(SOURCE_RELAY_IDX)
		self.close()

	def source_on(self):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(SOURCE_RELAY_IDX)
		self.close()

	def restart_artiq(self, t_wait=ARTIQ_RESTART_TIME_S, t_between=ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S):
		self.toggle_artiq_satellites_power(t_wait)
		time.sleep(t_between)
		self.toggle_artiq_main_power(t_wait)
		
	def toggle_artiq_main_power(self, t_wait=ARTIQ_RESTART_TIME_S):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(ARTIQ_MAIN_RELAY_IDX)
		self.close()
		
		time.sleep(t_wait)

		self.connect()
		_ = self.__board.turn_off_relay_by_index(ARTIQ_MAIN_RELAY_IDX)
		self.close()

	def toggle_artiq_satellites_power(self, t_wait=ARTIQ_RESTART_TIME_S):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(ARTIQ_SATELLITES_RELAY_IDX)
		self.close()
		
		time.sleep(t_wait)

		self.connect()
		_ = self.__board.turn_off_relay_by_index(ARTIQ_SATELLITES_RELAY_IDX)
		self.close()

	def artiq_satellites_on(self):
		self.connect()
		_ = self.__board.turn_off_relay_by_index(ARTIQ_SATELLITES_RELAY_IDX)
		self.close()

	def artiq_satellites_off(self):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(ARTIQ_SATELLITES_RELAY_IDX)
		self.close()

	def artiq_main_on(self):
		self.connect()
		_ = self.__board.turn_off_relay_by_index(ARTIQ_MAIN_RELAY_IDX)
		self.close()

	def artiq_main_off(self):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(ARTIQ_MAIN_RELAY_IDX)
		self.close()

	def enable_magnets(self):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(MAGNET_INHIBIT_IDX)
		self.close()

	def kill_magnets(self):
		self.connect()
		_ = self.__board.turn_off_relay_by_index(MAGNET_INHIBIT_IDX)
		self.close()

	def read_magnet_status(self):
		try:
			self.connect()
			out = bool(self.__board.get_relay_status_by_index(MAGNET_INHIBIT_IDX)[0])
			return out
		finally:
			self.close()
	
	def read_relay_status(self):
		try:
			self.connect()
			out = [True for _ in range(N_RELAYS)]
			for idx in range(N_RELAYS):
				out[idx] = bool(self.__board.get_relay_status_by_index(idx + 1)[0])
			return out
		finally:
			self.close()