"""Remote Control settings that must not live in this public repository.

The Google Voice number, the notification addresses and the whitelist (the phones and e-mail
addresses allowed to send commands) are kept in one JSON file on the lab's Google Drive, next to
the Gmail credentials (``REMOTE_CONTROL_CONFIG_FILEPATH`` in ``kexp.config.ip``)::

    {
      "gvoice_number": "8051234567",
      "slack_email": "channel-address@example.slack.com",
      "all_off_notification_recipient": "someone@example.com",
      "phones": [{"value": "8051234567", "label": "who"}],
      "emails": [{"value": "someone@example.com", "label": "who"}]
    }

Until 2026-09-28 the number and the addresses were constants in the code and the whitelist lived
in ``%data%\\remote_whitelist.json``. ``load_settings`` reads that old whitelist file (read-only)
when the Drive file holds no whitelist yet; the caller then saves, which moves it. The old file is
left where it is.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

SETTING_KEYS = ("gvoice_number", "slack_email", "all_off_notification_recipient")
WHITELIST_KEYS = ("phones", "emails")


class SettingsFileUnreadable(RuntimeError):
    """The settings file exists but cannot be parsed; saving over it would lose its other keys."""


def _read_json(path):
    """Return the parsed file, or None when it does not exist. Raise SettingsFileUnreadable when
    it exists but cannot be read or parsed."""
    if not path or not os.path.exists(path):
        return None
    try:
        # utf-8-sig: files saved on Windows may start with a byte-order mark
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as exc:
        raise SettingsFileUnreadable(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SettingsFileUnreadable(f"{path}: expected a JSON object, got {type(data).__name__}")
    return data


def load_settings(path, legacy_whitelist_path=None):
    """Read the settings. Returns ``(settings, whitelist_source)``.

    ``settings`` always has every key: the three strings (empty when unknown) and the two
    whitelist lists. ``whitelist_source`` is ``"drive"`` (the Drive file has a whitelist),
    ``"legacy"`` (taken from the old whitelist file), or ``"none"``. Never raises: an unreadable
    file is logged and treated as empty, so the panel still starts (with no whitelist, every
    command is refused).
    """
    settings = {k: "" for k in SETTING_KEYS}
    settings.update({k: [] for k in WHITELIST_KEYS})

    try:
        data = _read_json(path)
    except SettingsFileUnreadable as exc:
        logger.error(f"Remote Control settings unreadable ({exc}); running with no whitelist.")
        return settings, "none"
    if data is None:
        logger.warning(f"Remote Control settings file not found: {path}. "
                       f"Phone commands and notifications are off until it exists.")
    else:
        for k in SETTING_KEYS:
            settings[k] = str(data.get(k) or "").strip()
        for k in WHITELIST_KEYS:
            settings[k] = list(data.get(k) or [])
        if any(k in data for k in WHITELIST_KEYS):
            return settings, "drive"

    try:
        legacy = _read_json(legacy_whitelist_path)
    except SettingsFileUnreadable as exc:
        logger.error(f"Old whitelist file unreadable ({exc}); not migrated.")
        legacy = None
    if legacy is not None:
        for k in WHITELIST_KEYS:
            settings[k] = list(legacy.get(k) or [])
        return settings, "legacy"
    return settings, "none"


def save_whitelist(path, phones, emails):
    """Write the whitelist into the settings file, keeping every other key it holds.

    Raises SettingsFileUnreadable rather than overwrite a file it cannot parse.
    """
    data = _read_json(path) or {}
    data["phones"] = list(phones)
    data["emails"] = list(emails)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
