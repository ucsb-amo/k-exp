"""The device state file with every channel at the K machine's defaults.

``default_device_state()`` is the monitor server's ``state_generator`` (the
Device Control GUI's "Regenerate state file", status pill menu): the same
content ``generate_state_file.py`` writes -- the waxx Generator run over fresh
dds/ttl/dac frames -- but returned, not written. The monitor server writes it
(it owns the file) after copying the old one aside.

Never import ``generate_state_file`` for this: that script writes the file
when it is imported.
"""

from __future__ import annotations


def default_device_state() -> dict:
    """{"dds", "ttl", "dac", "metadata"} from fresh frames (their defaults)."""
    from waxx.util.device_state.generate_state_file import Generator  # noqa: PLC0415
    from kexp.config.dac_id import dac_frame  # noqa: PLC0415
    from kexp.config.dds_id import dds_frame  # noqa: PLC0415
    from kexp.config.ttl_id import ttl_frame  # noqa: PLC0415

    dac = dac_frame()
    gen = Generator(dds_frame=dds_frame(dac_frame_obj=dac), ttl_frame=ttl_frame(),
                    dac_frame=dac, state_file_path=None, verbose=False)
    gen.generate_device_config()
    return gen.config_data
