"""Does the tweezer AWG's software trigger apply queued tones?  (Run by hand.)

The monitor server holds the AWG between runs.  "Apply traps" writes the tones
through it and then pulses the AWG's hardware trigger (awg_trg_ttl) from the
monitor's kernel.  If the card's software trigger (M2CMD_CARD_FORCETRIGGER)
also executes the queued tones -- with the card's ext0-only trigger mask and
the DDS trigger source set to the card -- the server could apply tones without
the monitor experiment.  Spectrum's own DDS examples use it; nobody has
checked it on this card.  This script does, through the server's connection
(no second connection to the card, nothing through ARTIQ).

What you need: the monitor server running, the Tweezer AWG pill green on the
Composite tab, no run starting, and something showing the AWG's output --
a spectrum analyzer or scope on the AWG channel, before the AOD amplifier.
Leave the AOD RF switch (aod_rf_sw) OFF unless you mean to watch the tweezer
beams themselves; this script does not touch it.

    python kexp/experiments/tools/awg_force_trigger_check.py [--f1 72e6] [--f2 78e6] [--amp 0.05]

It writes tone f1 (no trigger), then force-triggers, then f2, then nothing,
asking you after each step what you saw.  It replaces whatever tones are
loaded now, and ends with none loaded (if it stops early on a refusal, the
last tones it wrote stay loaded -- "Apply traps" or disconnecting clears them).
"""
import argparse
import sys

from waxx.util.comms_server.comm_client import MonitorClient

KEY = "tweezer_awg"


def _call(client, cmd, **kwargs):
    reply = client.connection_call(KEY, cmd, kwargs)
    if reply is None:
        sys.exit(f"{cmd}: the monitor server did not answer.")
    if reply.get("status") != "ok":
        sys.exit(f"{cmd} refused: {reply.get('msg')}")
    return reply.get("result")


def _ask(prompt):
    return input(prompt + " [y/n] ").strip().lower().startswith("y")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--f1", type=float, default=72.e6, help="first tone (Hz)")
    parser.add_argument("--f2", type=float, default=78.e6, help="second tone (Hz)")
    parser.add_argument("--amp", type=float, default=0.05, help="tone amplitude (0-1)")
    args = parser.parse_args()
    if not 0. < args.amp <= 0.3:
        sys.exit("--amp must be in (0, 0.3] for this check")

    client = MonitorClient()
    status = client.get_status() or {}
    conn = (status.get("connections") or {}).get(KEY)
    if not conn or conn.get("state") != "connected":
        sys.exit(f"The monitor server does not hold the AWG: {conn}. Connect it on the "
                 f"Composite tab first.")
    print(f"AWG held by the monitor server: {conn.get('detail')}")
    print("Watch the AWG output.  The AOD RF switch is not touched by this script.\n")

    results = {}
    _call(client, "write_traps", rows=[[args.f1, args.amp]])
    results["write without trigger leaves the output alone"] = _ask(
        f"Wrote {args.f1 / 1e6:.3f} MHz WITHOUT a trigger.  Is the output UNCHANGED?")
    _call(client, "force_trigger")
    results["force trigger applies the tone"] = _ask(
        f"Software trigger sent.  Is {args.f1 / 1e6:.3f} MHz on the output now?")
    _call(client, "write_traps", rows=[[args.f2, args.amp]])
    _call(client, "force_trigger")
    results["a second force trigger applies the next tone"] = _ask(
        f"Wrote {args.f2 / 1e6:.3f} MHz and triggered.  Did the output move to it "
        f"({args.f1 / 1e6:.3f} gone)?")
    _call(client, "write_traps", rows=[])
    _call(client, "force_trigger")
    results["clearing the tones works"] = _ask("Cleared the tones and triggered.  "
                                               "Is the output off?")

    print("\nResult:")
    for what, ok in results.items():
        print(f"  {'yes' if ok else 'NO '}  {what}")
    print("\nThe AWG is left connected to the monitor server with no tones loaded.")


if __name__ == "__main__":
    main()
