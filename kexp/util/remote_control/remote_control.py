import json
import os

from kexp.config.ip import WHITELIST_PATH
from kexp.util.remote_control.command_handler import CommandHandler
from waxx.util.notifications import send_email, _load_credentials
import logging

ALS_STARTUP_SLACK_RECIPIENT = "general-aaaaahzr4dmblwquygpk47q6le@weldlab.slack.com"
ALS_STARTUP_SLACK_SUBJECT = "1064nm laser on in 3418"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ALL_OFF_NOTIFICATION_RECIPIENT = "herberthearsall@gmail.com"
def send_all_off_command():
    subject = "ALL OFF command executed"
    body = "All off command was run (all systems should be off)."
    try:
        send_email(ALL_OFF_NOTIFICATION_RECIPIENT, subject, body)
        logger.info("All off notification sent to %s: %s", ALL_OFF_NOTIFICATION_RECIPIENT, subject)
    except Exception as exc:
        logger.warning("Failed to send all off notification: %s", exc)

class RemoteControl(CommandHandler):
    def __init__(self):
        super().__init__()

        # Start with no server clients — the GUI buttons discover them in the background.
        self.als_client = None
        self.precilaser_client = None

        # label store: maps phone/email value → human label string
        self._labels: dict = {}

        # Load whitelist from JSON file (creates empty file on first run)
        self.load_whitelist_from_file()

        # Always allow the configured account to send commands to itself
        self.add_to_whitelist(self.email_handler.email_address)

        # Command handlers - maps keywords to handler functions
        self.add_command_handler(["sources","source","atoms"], self.handle_sources_command)
        self.add_command_handler(["als"], self.handle_als_command)
        self.add_command_handler(["preci", "precilaser"], self.handle_precilaser_command)
        self.add_command_handler(["all"], self.handle_all_command)

    def load_whitelist_from_file(self):
        """Load whitelist from JSON file.

        Supports both old format (plain strings) and new format
        ({"value": ..., "label": ...} objects).  Creates an empty file if absent.
        """
        if not os.path.exists(WHITELIST_PATH):
            logger.info(f"Whitelist file not found — creating empty file at {WHITELIST_PATH}")
            data = {"phones": [], "emails": []}
            try:
                os.makedirs(os.path.dirname(WHITELIST_PATH), exist_ok=True)
                with open(WHITELIST_PATH, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception as exc:
                logger.warning(f"Could not write whitelist file: {exc}")
        else:
            try:
                with open(WHITELIST_PATH, "r") as f:
                    data = json.load(f)
            except Exception as exc:
                logger.error(f"Could not read whitelist file: {exc} — using empty whitelist")
                return

        def _entry(item):
            """Return (value, label) from either a plain string or a dict entry."""
            if isinstance(item, dict):
                return item.get("value", ""), item.get("label", "")
            return str(item), ""

        for item in data.get("phones", []):
            value, label = _entry(item)
            if value:
                self.add_to_whitelist(value)
                self._labels[value] = label
        for item in data.get("emails", []):
            value, label = _entry(item)
            if value:
                self.add_to_whitelist(value)
                self._labels[value] = label
        logger.info(
            f"Loaded {len(data.get('phones', []))} phones and "
            f"{len(data.get('emails', []))} emails from whitelist."
        )

    def save_whitelist_to_file(self):
        """Persist the current in-memory whitelist back to the JSON file."""
        def _obj(value):
            return {"value": value, "label": self._labels.get(value, "")}

        data = {
            "phones": [_obj(p) for p in self.email_handler.phone_whitelist],
            "emails": [
                _obj(addr) for addr in self.email_handler.whitelist
                if not addr.endswith("@txt.voice.google.com")
            ],
        }
        try:
            os.makedirs(os.path.dirname(WHITELIST_PATH), exist_ok=True)
            with open(WHITELIST_PATH, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Whitelist saved to {WHITELIST_PATH}")
        except Exception as exc:
            logger.error(f"Could not save whitelist: {exc}")

    def send_als_startup_notification(self):
        """Send ALS startup notification via Slack email."""
        send_email(ALS_STARTUP_SLACK_RECIPIENT, ALS_STARTUP_SLACK_SUBJECT, ALS_STARTUP_SLACK_SUBJECT)

    def handle_sources_command(self, value):
        """
        Handle the 'sources' command to turn sources on or off
        """
        try:
            on_values = ["on", "1", "true", "t"]
            off_values = ["off", "0", "false", "f"]

            value_lower = value.strip().lower()
            if value_lower in on_values:
                self.ethernet_relay.source_on()
                return "Sources successfully turned ON"
            
            elif value_lower in off_values:
                self.ethernet_relay.source_off()
                return "Sources successfully turned OFF"
            else:
                logger.warning(f"Invalid sources command value: {value}")
                return f"Invalid sources command value: {value}."
            
        except Exception as e:
            logger.error(f"Error controlling sources: {e}")
            return f"Error controlling sources: {e}"

    def handle_als_command(self, value):
        """Handle ALS startup/shutdown commands sent through remote control."""
        if self.als_client is None:
            return "ALS server not connected"
        try:
            value_lower = value.strip().lower()

            startup_values = {"on", "1", "start"}
            shutdown_values = {"off", "0", "shutdown"}

            if value_lower in startup_values:
                ok = self.als_client.run_startup_sequence()
                if ok:
                    try:
                        # self.send_als_startup_notification()
                        pass
                    except Exception as exc:
                        logger.warning(f"ALS startup succeeded, but Slack notification failed: {exc}")
                    return "ALS startup sequence requested"
                return "ALS server did not acknowledge startup request"

            if value_lower in shutdown_values:
                ok = self.als_client.run_shutdown_sequence()
                if ok:
                    return "ALS shutdown sequence requested"
                return "ALS server did not acknowledge shutdown request"

            return (
                "Invalid ALS command value. Use one of: "
                "on, 1, start, off, 0, shutdown"
            )
        except Exception as exc:
            logger.error(f"Error sending ALS command: {exc}")
            return f"Error sending ALS command: {exc}"

    def handle_precilaser_command(self, value):
        """Handle Precilaser startup/shutdown commands sent through remote control."""
        if self.precilaser_client is None:
            return "Precilaser server not connected"
        try:
            value_lower = value.strip().lower()

            startup_values = {"on", "1", "start"}
            shutdown_values = {"off", "0", "shutdown"}

            if value_lower in startup_values:
                ok = self.precilaser_client.run_startup_sequence()
                if ok:
                    return "Precilaser startup sequence requested"
                return "Precilaser server did not acknowledge startup request"

            if value_lower in shutdown_values:
                ok = self.precilaser_client.run_shutdown_sequence()
                if ok:
                    return "Precilaser shutdown sequence requested"
                return "Precilaser server did not acknowledge shutdown request"

            return (
                "Invalid Precilaser command value. Use one of: "
                "on, 1, start, off, 0, shutdown"
            )
        except Exception as exc:
            logger.error(f"Error sending Precilaser command: {exc}")
            return f"Error sending Precilaser command: {exc}"

    def handle_all_command(self, value):
        """Handle master command to control all systems (sources, ALS, Precilaser)."""
        try:
            value_lower = value.strip().lower()

            startup_values = {"on", "1", "start"}
            shutdown_values = {"off", "0", "shutdown"}

            results = []

            if value_lower in startup_values:
                # Turn on sources
                try:
                    self.ethernet_relay.source_on()
                    results.append("Sources ON")
                except Exception as exc:
                    logger.warning(f"Failed to turn on sources: {exc}")
                    results.append(f"Sources failed ({exc})")

                # Start ALS ramp up
                try:
                    ok = self.als_client.run_startup_sequence()
                    results.append("ALS ramp ON" if ok else "ALS ramp failed")
                except Exception as exc:
                    logger.warning(f"Failed to start ALS ramp up: {exc}")
                    results.append(f"ALS failed ({exc})")

                # Start Precilaser ramp up
                try:
                    ok = self.precilaser_client.run_startup_sequence()
                    results.append("Precilaser ramp ON" if ok else "Precilaser ramp failed")
                except Exception as exc:
                    logger.warning(f"Failed to start Precilaser ramp up: {exc}")
                    results.append(f"Precilaser failed ({exc})")

                return "All systems startup: " + "; ".join(results)

            if value_lower in shutdown_values:
                # Turn off sources
                try:
                    self.ethernet_relay.source_off()
                    results.append("Sources OFF")
                except Exception as exc:
                    logger.warning(f"Failed to turn off sources: {exc}")
                    results.append(f"Sources failed ({exc})")

                # Start ALS ramp down
                try:
                    ok = self.als_client.run_shutdown_sequence()
                    results.append("ALS ramp OFF" if ok else "ALS ramp failed")
                except Exception as exc:
                    logger.warning(f"Failed to start ALS ramp down: {exc}")
                    results.append(f"ALS failed ({exc})")

                # Start Precilaser ramp down
                try:
                    ok = self.precilaser_client.run_shutdown_sequence()
                    results.append("Precilaser ramp OFF" if ok else "Precilaser ramp failed")
                except Exception as exc:
                    logger.warning(f"Failed to start Precilaser ramp down: {exc}")
                    results.append(f"Precilaser failed ({exc})")

                return "All systems shutdown: " + "; ".join(results)

            return (
                "Invalid all command value. Use one of: "
                "on, 1, start, off, 0, shutdown"
            )
        except Exception as exc:
            logger.error(f"Error in all command: {exc}")
            return f"Error in all command: {exc}"
        
def main():
    """Main function to run the remote control GUI."""
    import sys
    from PyQt6.QtWidgets import QApplication
    from kexp.util.remote_control.remote_control_gui import RemoteControlGUI

    app = QApplication(sys.argv)
    controller = RemoteControl()
    window = RemoteControlGUI(controller)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
