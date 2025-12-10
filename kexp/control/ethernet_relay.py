import time

from waxx.control.ethernet_relay import EthernetRelay as EthernetRelayWaxx

from kexp.config.ip import ETHERNET_RELAY_IP, ETHERNET_RELAY_PORT

N_RELAYS = 4

MAGNET_INHIBIT_IDX = 2
SOURCE_RELAY_IDX = 3
ARTIQ_RELAY_IDX = 4

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

	def toggle_artiq_power(self):
		self.connect()
		_ = self.__board.turn_on_relay_by_index(ARTIQ_RELAY_IDX)
		self.close()
		
		time.sleep(3.)

		self.connect()
		_ = self.__board.turn_off_relay_by_index(ARTIQ_RELAY_IDX)
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