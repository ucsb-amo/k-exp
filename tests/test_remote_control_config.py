"""Remote Control settings kept off GitHub (kexp.util.remote_control.rc_config): the Google Voice
number, the notification addresses and the whitelist come from a file on the lab's Google Drive,
the old whitelist file is moved into it once, and saving never loses the other keys.

Everything runs on temporary files with made-up numbers; the ethernet relay and the Gmail
credentials are replaced, so nothing touches the network, the Drive or the data drive.
"""
import json

import pytest

from kexp.util.remote_control import rc_config

GV = "5550001111"
PHONE = "5550002222"
MAIL = "someone@example.com"


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_the_drive_file_supplies_every_setting_and_the_whitelist(tmp_path):
    drive = tmp_path / "remote_control.json"
    _write(drive, {"gvoice_number": GV, "slack_email": "chan@example.com",
                   "all_off_notification_recipient": MAIL,
                   "phones": [{"value": PHONE, "label": "a"}], "emails": [MAIL]})
    settings, source = rc_config.load_settings(str(drive), str(tmp_path / "old.json"))
    assert source == "drive"
    assert settings["gvoice_number"] == GV and settings["slack_email"] == "chan@example.com"
    assert settings["phones"] == [{"value": PHONE, "label": "a"}] and settings["emails"] == [MAIL]


def test_the_old_whitelist_is_used_when_the_drive_file_has_none(tmp_path):
    drive = tmp_path / "remote_control.json"
    old = tmp_path / "old.json"
    _write(drive, {"gvoice_number": GV})
    _write(old, {"phones": [PHONE], "emails": [MAIL]})
    settings, source = rc_config.load_settings(str(drive), str(old))
    assert source == "legacy"
    assert settings["gvoice_number"] == GV and settings["phones"] == [PHONE]


def test_nothing_found_gives_empty_settings(tmp_path):
    settings, source = rc_config.load_settings(str(tmp_path / "a.json"), str(tmp_path / "b.json"))
    assert source == "none"
    assert settings["gvoice_number"] == "" and settings["phones"] == [] and settings["emails"] == []


def test_saving_keeps_the_other_keys(tmp_path):
    drive = tmp_path / "remote_control.json"
    _write(drive, {"gvoice_number": GV, "slack_email": "chan@example.com", "phones": []})
    rc_config.save_whitelist(str(drive), [{"value": PHONE, "label": ""}], [])
    data = json.loads(drive.read_text(encoding="utf-8"))
    assert data["gvoice_number"] == GV and data["slack_email"] == "chan@example.com"
    assert data["phones"] == [{"value": PHONE, "label": ""}] and data["emails"] == []


def test_an_unreadable_file_is_never_overwritten(tmp_path):
    drive = tmp_path / "remote_control.json"
    drive.write_text("{not json", encoding="utf-8")
    settings, source = rc_config.load_settings(str(drive))
    assert source == "none" and settings["phones"] == []
    with pytest.raises(rc_config.SettingsFileUnreadable):
        rc_config.save_whitelist(str(drive), [], [])
    assert drive.read_text(encoding="utf-8") == "{not json"


@pytest.fixture
def offline_remote_control(monkeypatch):
    """RemoteControl with the relay and the Gmail credentials replaced (no network, no Drive)."""
    from kexp.util.remote_control import command_handler, email_handler, remote_control
    monkeypatch.setattr(command_handler, "EthernetRelay", lambda *a, **k: object())
    monkeypatch.setattr(email_handler, "_load_credentials", lambda *a, **k: ("lab@example.com", "x"))
    return remote_control.RemoteControl


def test_the_old_whitelist_moves_into_the_drive_file_and_texts_are_accepted(tmp_path, offline_remote_control):
    drive = tmp_path / "remote_control.json"
    old = tmp_path / "old.json"
    _write(drive, {"gvoice_number": GV, "slack_email": "chan@example.com"})
    _write(old, {"phones": [{"value": PHONE, "label": "a"}], "emails": [MAIL]})
    old_text = old.read_text(encoding="utf-8")

    rc = offline_remote_control(settings_path=str(drive), legacy_whitelist_path=str(old))

    data = json.loads(drive.read_text(encoding="utf-8"))
    assert data["gvoice_number"] == GV and data["slack_email"] == "chan@example.com"
    assert {"value": PHONE, "label": "a"} in data["phones"]
    assert MAIL in [e["value"] for e in data["emails"]]
    assert old.read_text(encoding="utf-8") == old_text          # the old file is left alone
    assert rc.email_handler.gvoice_number == GV
    assert rc.email_handler.is_sender_whitelisted(f"1{GV}.1{PHONE}.abcd@txt.voice.google.com")
    assert not rc.email_handler.is_sender_whitelisted(f"1{GV}.15550009999.abcd@txt.voice.google.com")


def test_without_a_google_voice_number_phones_are_kept_but_texts_refused(tmp_path, offline_remote_control):
    drive = tmp_path / "remote_control.json"
    _write(drive, {"phones": [PHONE], "emails": []})

    rc = offline_remote_control(settings_path=str(drive), legacy_whitelist_path=str(tmp_path / "none.json"))
    rc.save_whitelist_to_file()

    data = json.loads(drive.read_text(encoding="utf-8"))
    assert PHONE in [p["value"] for p in data["phones"]]
    assert not rc.email_handler.is_sender_whitelisted(f"1{GV}.1{PHONE}.abcd@txt.voice.google.com")
