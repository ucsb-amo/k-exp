"""The lab's per-shot OPX sequences, one topic per module.

Import the sequence object and hand it to the experiment:

    from kexp.experiments.opx_sequences.rabi import rabi_raman_pulse
    ...
    self.opx.use(rabi_raman_pulse)

Defining a sequence inline in an experiment file works the same way -- the
@opx_sequence decorator returns the object to pass to use(). Keep anything
worth reusing here, where both the sequence and its users are readable in
one place.
"""
