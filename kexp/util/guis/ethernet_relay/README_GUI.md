# Ethernet Relay panel

The Ethernet Relay panel (in the server dashboard, client dashboards, or standalone via
`run_relay_gui.py` / `_bat/ethernet_relay_gui.bat`) shows and switches the K ethernet relay:
K sources, magnet enable, ARTIQ main / satellite crate power.

## Who talks to the relay

The relay board (NCD RelayPro, 192.168.1.109:2101) takes **one TCP connection at a time**.
Since 2026-11-17 the **interlock server is its only user**; this panel, remote control,
notebooks and scripts ask the interlock server (`kexp.control.ethernet_relay.EthernetRelay`,
the client). The panel's status read is the relay state the interlock server last read
(it polls every 5 s); opening more panels adds no relay traffic.

- **Magnet button**: "INH - Reset?" sends the interlock's `ENABLE_MAGNETS`, so it is
  refused while the interlock is tripped, before PLC data arrives, while the relay is not
  answering, or during a magnet kill; the panel says why. "ON" sends `DISABLE_MAGNETS`.
- **ARTIQ restart**: runs on the interlock server as one job (satellites, then main, for
  the full restart). A restart the server has to abort (it is stopped) restores the
  crates' power first.
- **Interlock server not running**: the panel shows ERROR. Switching off (magnet kill,
  source off) from a script still works — the client then goes to the relay directly.
- **An interlock server older than 2026-11-17**: the panel reads and switches the relay
  directly, as before.

## Command line

```
python -m kexp.control.ethernet_relay status
python -m kexp.control.ethernet_relay source on|off
python -m kexp.control.ethernet_relay magnets on|off
python -m kexp.control.ethernet_relay artiq-restart all|main|satellites [--t-wait S] [--t-between S]
```

## Channels

| Relay | Energised means |
|---|---|
| 1 | ARTIQ main crate power cut |
| 2 | magnets enabled |
| 3 | K sources on |
| 4 | ARTIQ satellite crates power cut |
