"""The K-machine ethernet relay (NCD RelayPro, 4 channels, 192.168.1.109:2101).

The board takes ONE TCP connection at a time, so one process owns it: the
interlock server (``kexp.util.guis.interlock``).  Everyone else asks that
server.

* :class:`EthernetRelay` -- the client.  Same methods as the old direct class
  (``source_on``/``source_off``, ``restart_artiq``, ``read_relay_status``, ...),
  so ``from kexp import EthernetRelay; EthernetRelay().source_off()`` keeps
  working.  It talks to the interlock server.
* :class:`EthernetRelayDirect` -- the board itself.  Only the interlock server
  uses it, plus two fallbacks of the client: an interlock server too old to
  know the relay commands (today's behaviour), and a magnet kill or source off
  when no interlock server is running (switching something off is always safe;
  a rare collision costs nothing).

Channels (relay energised = ...):
  1 ARTIQ main crate power CUT     2 magnets ENABLED
  3 K sources ON                   4 ARTIQ satellite crates power CUT

Command line (talks to the interlock server)::

    python -m kexp.control.ethernet_relay status
    python -m kexp.control.ethernet_relay source off
    python -m kexp.control.ethernet_relay magnets off
    python -m kexp.control.ethernet_relay artiq-restart all
"""
from __future__ import annotations

import contextlib
import logging
import time
from typing import Optional

from waxx.control.ethernet_relay import EthernetRelay as EthernetRelayWaxx

from kexp.config.ip import ETHERNET_RELAY_IP, ETHERNET_RELAY_PORT

_LOG = logging.getLogger("kexp.control.ethernet_relay")

N_RELAYS = 4

ARTIQ_MAIN_RELAY_IDX = 1
MAGNET_INHIBIT_IDX = 2
SOURCE_RELAY_IDX = 3
ARTIQ_SATELLITES_RELAY_IDX = 4

ARTIQ_RESTART_TIME_S = 3.
ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S = 5.

#: Channel names used on the wire (interlock server commands, snapshots).
CHANNEL_NAMES = {
	ARTIQ_MAIN_RELAY_IDX: "artiq_main_power_cut",
	MAGNET_INHIBIT_IDX: "magnet_enabled",
	SOURCE_RELAY_IDX: "source_on",
	ARTIQ_SATELLITES_RELAY_IDX: "artiq_satellites_power_cut",
}
CHANNEL_INDEX = {name: idx for idx, name in CHANNEL_NAMES.items()}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class RelayError(RuntimeError):
	"""A relay request did not do what was asked."""


class RelayServerUnavailable(RelayError):
	"""No interlock server answered (not running, or not reachable)."""


class RelayServerTooOld(RelayError):
	"""The interlock server answering does not know the relay commands."""


class RelayRefused(RelayError):
	"""The interlock server refused the request (the reason is the message)."""

	def __init__(self, reason: str, message: str = ""):
		self.reason = reason
		super().__init__(f"{reason}: {message}" if message else reason)


class RelayCommandFailed(RelayError):
	"""The request reached the server but the relay did not confirm it."""


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

class EthernetRelayDirect(EthernetRelayWaxx):
	"""Direct TCP access to the board.  Only the interlock server (the owner)
	and the client's documented fallbacks use this; a second process using it
	while the server runs collides with the server (the board takes one
	connection at a time).

	Every method is one contact: connect, its commands, close.  ``retries`` /
	``timeout`` are the connect policy (default: 5 retries, 10 s); the owner
	passes ``retries=0`` and a contact budget, which also bounds every read.
	"""

	def __init__(self, relay_ip=None, port=None):
		super().__init__(relay_ip=relay_ip or ETHERNET_RELAY_IP,
						 port=port or ETHERNET_RELAY_PORT)

	@contextlib.contextmanager
	def session(self, retries=None, timeout=None):
		"""One contact: ``with relay.session(...) as board: ...``.  With
		``retries=0`` the timeout is the whole contact's budget."""
		deadline_s = timeout if (retries == 0 and timeout is not None) else None
		self.connect(retries=retries, timeout=timeout, deadline_s=deadline_s)
		try:
			yield self.board
		finally:
			self.close()

	# --- board-level helpers (inside a session) -------------------------

	@staticmethod
	def _write(board, idx, on):
		if on:
			ok, _ = board.turn_on_relay_by_index(idx)
		else:
			ok, _ = board.turn_off_relay_by_index(idx)
		if not ok:
			raise RelayCommandFailed(f"relay {idx}: the board did not acknowledge the write")

	@staticmethod
	def _read(board, idx):
		reply = board.get_relay_status_by_index(idx)
		if reply is False or not reply:
			raise RelayCommandFailed(f"relay {idx}: bad status reply from the board")
		return bool(reply[0])

	@classmethod
	def _read_all(cls, board):
		return [cls._read(board, idx + 1) for idx in range(N_RELAYS)]

	# --- one-contact operations --------------------------------------------

	def read_relay_status(self, retries=None, timeout=None):
		"""States of relays 1-4 (True = energised)."""
		with self.session(retries, timeout) as board:
			return self._read_all(board)

	def read_magnet_status(self, retries=None, timeout=None):
		with self.session(retries, timeout) as board:
			return self._read(board, MAGNET_INHIBIT_IDX)

	def read_source_status(self, retries=None, timeout=None):
		with self.session(retries, timeout) as board:
			return self._read(board, SOURCE_RELAY_IDX)

	def set_channel(self, idx, on, retries=None, timeout=None):
		with self.session(retries, timeout) as board:
			self._write(board, idx, on)

	def set_channel_and_read_all(self, idx, on, retries=None, timeout=None):
		"""Write one relay and read all four back, in one contact."""
		with self.session(retries, timeout) as board:
			self._write(board, idx, on)
			return self._read_all(board)

	def set_channels_and_read_all(self, states, retries=None, timeout=None):
		"""Write several relays ({idx: on}) and read all four back, in one contact."""
		with self.session(retries, timeout) as board:
			for idx, on in states.items():
				self._write(board, idx, on)
			return self._read_all(board)

	def kill_magnets_and_read(self, retries=None, timeout=None):
		"""Magnet relay off and read it back, in one contact.  Returns True if
		the magnets still read enabled."""
		with self.session(retries, timeout) as board:
			self._write(board, MAGNET_INHIBIT_IDX, False)
			return self._read(board, MAGNET_INHIBIT_IDX)

	def source_off(self, retries=None, timeout=None):
		self.set_channel(SOURCE_RELAY_IDX, False, retries, timeout)

	def source_on(self, retries=None, timeout=None):
		self.set_channel(SOURCE_RELAY_IDX, True, retries, timeout)

	def enable_magnets(self, retries=None, timeout=None):
		self.set_channel(MAGNET_INHIBIT_IDX, True, retries, timeout)

	def kill_magnets(self, retries=None, timeout=None):
		self.set_channel(MAGNET_INHIBIT_IDX, False, retries, timeout)

	def artiq_satellites_on(self):
		self.set_channel(ARTIQ_SATELLITES_RELAY_IDX, False)

	def artiq_satellites_off(self):
		self.set_channel(ARTIQ_SATELLITES_RELAY_IDX, True)

	def artiq_main_on(self):
		self.set_channel(ARTIQ_MAIN_RELAY_IDX, False)

	def artiq_main_off(self):
		self.set_channel(ARTIQ_MAIN_RELAY_IDX, True)

	def toggle_artiq_main_power(self, t_wait=ARTIQ_RESTART_TIME_S):
		self.set_channel(ARTIQ_MAIN_RELAY_IDX, True)
		time.sleep(t_wait)
		self.set_channel(ARTIQ_MAIN_RELAY_IDX, False)

	def toggle_artiq_satellites_power(self, t_wait=ARTIQ_RESTART_TIME_S):
		self.set_channel(ARTIQ_SATELLITES_RELAY_IDX, True)
		time.sleep(t_wait)
		self.set_channel(ARTIQ_SATELLITES_RELAY_IDX, False)

	def restart_artiq(self, t_wait=ARTIQ_RESTART_TIME_S, t_between=ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S):
		self.toggle_artiq_satellites_power(t_wait)
		time.sleep(t_between)
		self.toggle_artiq_main_power(t_wait)


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------

def _is_unknown_command(reply: dict) -> bool:
	return (reply.get("status") == "error"
			and str(reply.get("message", "")).lower().startswith("unknown command"))


class EthernetRelay:
	"""The relay, through the interlock server.  Drop-in for the old class.

	* Switching something OFF (``kill_magnets``, ``source_off``) keeps trying
	  for up to ``SAFE_RETRY_BUDGET_S`` and, when no interlock server can be
	  reached, goes to the board directly.
	* ``enable_magnets`` goes through the interlock's checks (refused while
	  tripped, before PLC data, while the relay is not answering): raises
	  :class:`RelayRefused` with the reason.
	* Reads return the relay's state as the server last read it (fresh=True,
	  the default for reads, asks the server to read it now).
	* An interlock server that does not know the relay commands (an old one):
	  the request goes to the board directly, as before.

	``retries`` / ``timeout`` arguments are accepted for compatibility and
	ignored.  ``connect()`` / ``close()`` do nothing.
	"""

	IS_RELAY_CLIENT = True          # the owner refuses to be built on a client
	SAFE_RETRY_BUDGET_S = 60.0
	RPC_TIMEOUT_S = 10.0            # a write waits for the lock, writes, reads back
	STATUS_TIMEOUT_S = 6.0
	RETRY_GAP_S = 1.0
	JOB_POLL_S = 0.5

	def __init__(self, discovery_timeout: float = 3.0, client=None, direct_factory=None):
		self._discovery_timeout = float(discovery_timeout)
		self._client = client                       # discovered lazily
		self._direct_factory = direct_factory or EthernetRelayDirect
		self._direct = None

	# --- plumbing -------------------------------------------------------------

	def _interlock(self):
		if self._client is None:
			from kexp.util.guis.interlock.interlock_client import InterlockClient  # noqa: PLC0415
			try:
				self._client = InterlockClient(discovery_timeout=self._discovery_timeout,
											   timeout=self.RPC_TIMEOUT_S)
			except RuntimeError as exc:
				raise RelayServerUnavailable(f"interlock server not found: {exc}") from exc
		return self._client

	def _board(self):
		if self._direct is None:
			self._direct = self._direct_factory()
		return self._direct

	def _request(self, obj: dict, timeout: float) -> dict:
		"""One JSON request.  Raises RelayServerUnavailable on no server / a
		network failure, RelayServerTooOld on an old server."""
		client = self._interlock()
		try:
			reply = client.request(obj, timeout=timeout)
		except OSError as exc:
			raise RelayServerUnavailable(f"interlock server did not answer: {exc!r}") from exc
		if _is_unknown_command(reply):
			raise RelayServerTooOld("the interlock server does not know the relay commands")
		return reply

	def _bare(self, command: str, timeout: float) -> dict:
		client = self._interlock()
		try:
			return client.send_command(command, timeout=timeout)
		except OSError as exc:
			raise RelayServerUnavailable(f"interlock server did not answer: {exc!r}") from exc

	def _switch_off_safely(self, what: str, server_call, direct_call):
		"""Retry the server for up to SAFE_RETRY_BUDGET_S, then the board."""
		t_end = time.monotonic() + self.SAFE_RETRY_BUDGET_S
		last = None
		while True:
			try:
				reply = server_call()
				if reply.get("status") == "ok":
					return
				last = RelayCommandFailed(f"{what}: {reply.get('message') or reply.get('status')}")
			except RelayServerTooOld:
				direct_call()
				return
			except RelayServerUnavailable as exc:
				last = exc
				if self._client is None:
					# No interlock server at all: nobody owns the board.
					_LOG.warning("%s: %s -- going to the relay directly", what, exc)
					direct_call()
					return
			if time.monotonic() >= t_end:
				break
			time.sleep(self.RETRY_GAP_S)
		_LOG.warning("%s: no confirmation from the interlock server in %.0f s (%s) -- "
					 "trying the relay directly", what, self.SAFE_RETRY_BUDGET_S, last)
		try:
			direct_call()
		except Exception as exc:
			raise RelayCommandFailed(f"{what} failed through the interlock server ({last}) "
									 f"and directly ({exc!r})") from exc

	def _set(self, channel: str, on: bool) -> list:
		try:
			reply = self._request({"cmd": "relay_set", "channel": channel, "on": bool(on)},
								  self.RPC_TIMEOUT_S)
		except RelayServerTooOld:
			self._board().set_channel(CHANNEL_INDEX[channel], on)
			return self._board().read_relay_status()
		if reply.get("status") == "refused":
			raise RelayRefused(reply.get("reason", "refused"), reply.get("message", ""))
		if reply.get("status") != "ok":
			raise RelayCommandFailed(f"{channel} -> {'on' if on else 'off'}: "
									 f"{reply.get('message') or reply.get('status')}")
		return reply.get("states")

	def _status(self, fresh: bool) -> list:
		try:
			reply = self._request({"cmd": "relay_status", "fresh": bool(fresh)},
								  self.STATUS_TIMEOUT_S)
		except RelayServerTooOld:
			# As the old panels read it: one short attempt.
			return self._board().read_relay_status(retries=0, timeout=3.0)
		states = reply.get("states")
		if reply.get("status") != "ok" or states is None:
			raise RelayCommandFailed(f"relay status: {reply.get('message') or reply.get('status')}")
		return [bool(s) for s in states]

	def _restart(self, which: str, t_wait: float, t_between: float, direct_call):
		try:
			reply = self._request({"cmd": "artiq_restart", "which": which,
								   "t_wait": float(t_wait), "t_between": float(t_between)},
								  self.RPC_TIMEOUT_S)
		except RelayServerTooOld:
			direct_call()
			return
		if reply.get("status") != "started":
			raise RelayCommandFailed(f"ARTIQ restart ({which}) not started: "
									 f"{reply.get('message') or reply.get('status')}")
		job_id = reply["job_id"]
		t_end = time.monotonic() + 2 * float(t_wait) + float(t_between) + 60.0
		while time.monotonic() < t_end:
			time.sleep(self.JOB_POLL_S)
			try:
				job = self._request({"cmd": "relay_job", "job_id": job_id}, self.STATUS_TIMEOUT_S)
			except RelayServerUnavailable:
				continue                  # keep asking until the deadline
			state = job.get("state")
			if state == "done":
				return
			if state in ("failed", "aborted", "unknown"):
				raise RelayCommandFailed(f"ARTIQ restart ({which}) {state}: {job.get('error')}")
		raise RelayCommandFailed(f"ARTIQ restart ({which}): no result from the interlock server "
								 f"by the deadline (job {job_id})")

	# --- the old public methods ---------------------------------------------

	def connect(self, *args, **kwargs):
		"""Nothing to do (the interlock server holds the connection)."""

	def close(self):
		"""Nothing to do."""

	def read_relay_status(self, retries=None, timeout=None, fresh=True):
		return self._status(fresh)

	def read_magnet_status(self, retries=None, timeout=None, fresh=True):
		return self._status(fresh)[MAGNET_INHIBIT_IDX - 1]

	def read_source_status(self, retries=None, timeout=None, fresh=True):
		return self._status(fresh)[SOURCE_RELAY_IDX - 1]

	def source_on(self):
		self._set("source_on", True)

	def source_off(self):
		self._switch_off_safely(
			"source off",
			lambda: self._request({"cmd": "relay_set", "channel": "source_on", "on": False},
								  self.RPC_TIMEOUT_S),
			lambda: self._board().source_off())

	def kill_magnets(self):
		self._switch_off_safely(
			"magnet kill",
			lambda: self._bare("DISABLE_MAGNETS", self.RPC_TIMEOUT_S),
			lambda: self._board().kill_magnets())

	def enable_magnets(self):
		reply = self._bare("ENABLE_MAGNETS", self.RPC_TIMEOUT_S)
		if reply.get("status") == "refused":
			raise RelayRefused(reply.get("reason", "refused"), reply.get("message", ""))
		if reply.get("status") != "ok":
			raise RelayCommandFailed(f"magnet enable: {reply.get('message') or reply.get('status')}")

	def artiq_satellites_on(self):
		self._set("artiq_satellites_power_cut", False)

	def artiq_satellites_off(self):
		self._set("artiq_satellites_power_cut", True)

	def artiq_main_on(self):
		self._set("artiq_main_power_cut", False)

	def artiq_main_off(self):
		self._set("artiq_main_power_cut", True)

	def restart_artiq(self, t_wait=ARTIQ_RESTART_TIME_S, t_between=ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S):
		self._restart("all", t_wait, t_between,
					  lambda: self._board().restart_artiq(t_wait, t_between))

	def toggle_artiq_main_power(self, t_wait=ARTIQ_RESTART_TIME_S):
		self._restart("main", t_wait, 0.0,
					  lambda: self._board().toggle_artiq_main_power(t_wait))

	def toggle_artiq_satellites_power(self, t_wait=ARTIQ_RESTART_TIME_S):
		self._restart("satellites", t_wait, 0.0,
					  lambda: self._board().toggle_artiq_satellites_power(t_wait))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _format_states(states) -> str:
	return ", ".join(f"{CHANNEL_NAMES[i + 1]}={'yes' if s else 'no'}" for i, s in enumerate(states))


def main(argv: Optional[list] = None) -> int:
	import argparse  # noqa: PLC0415
	p = argparse.ArgumentParser(
		prog="python -m kexp.control.ethernet_relay",
		description="The K ethernet relay, through the interlock server.")
	sub = p.add_subparsers(dest="what", required=True)
	sub.add_parser("status", help="relay states as the interlock server reads them")
	s = sub.add_parser("source", help="K sources on/off")
	s.add_argument("state", choices=["on", "off"])
	m = sub.add_parser("magnets", help="magnets off (kill) / on (through the interlock's checks)")
	m.add_argument("state", choices=["on", "off"])
	r = sub.add_parser("artiq-restart", help="power-cycle ARTIQ crates (satellites first for 'all')")
	r.add_argument("which", choices=["all", "main", "satellites"])
	r.add_argument("--t-wait", type=float, default=ARTIQ_RESTART_TIME_S)
	r.add_argument("--t-between", type=float, default=ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S)
	args = p.parse_args(argv)

	relay = EthernetRelay()
	try:
		if args.what == "status":
			print(_format_states(relay.read_relay_status()))
		elif args.what == "source":
			relay.source_on() if args.state == "on" else relay.source_off()
			print(_format_states(relay.read_relay_status()))
		elif args.what == "magnets":
			relay.enable_magnets() if args.state == "on" else relay.kill_magnets()
			print(_format_states(relay.read_relay_status()))
		elif args.what == "artiq-restart":
			if args.which == "all":
				relay.restart_artiq(args.t_wait, args.t_between)
			elif args.which == "main":
				relay.toggle_artiq_main_power(args.t_wait)
			else:
				relay.toggle_artiq_satellites_power(args.t_wait)
			print(_format_states(relay.read_relay_status()))
	except RelayError as exc:
		print(f"refused or failed: {exc}")
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
