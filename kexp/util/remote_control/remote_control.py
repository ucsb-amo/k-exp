from kexp.util.remote_control.command_handler import CommandHandler
from waxx.util.guis.als.als_gui_client import ALSGuiClient
from waxx.util.guis.precilaser.precilaser_gui_client import PrecilaserGuiClient
from kexp.config.ip import ALS_SERVER_IP, ALS_SERVER_PORT, PRECILASER_SERVER_IP, PRECILASER_SERVER_PORT
from waxx.util.notifications import send_email, _load_credentials
import logging

ALS_STARTUP_SLACK_RECIPIENT = "general-aaaaahzr4dmblwquygpk47q6le@weldlab.slack.com"
ALS_STARTUP_SLACK_SUBJECT = "1064nm laser on in 3418"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def send_all_off_command():
    email, _ = _load_credentials()
    send_email(email, "all off", "all off")

class RemoteControl(CommandHandler):
    def __init__(self):
        super().__init__()

        self.als_client = ALSGuiClient(host=ALS_SERVER_IP, port=ALS_SERVER_PORT)
        self.precilaser_client = PrecilaserGuiClient(host=PRECILASER_SERVER_IP, port=PRECILASER_SERVER_PORT)

        # Whitelist of approved phone numbers (10 digits, no delimiters)
        self.add_to_whitelist("9165834119")
        self.add_to_whitelist("5104069659")
        self.add_to_whitelist("7022366997")
        self.add_to_whitelist("8052848029")
        self.add_to_whitelist("8052847408")
        
        # Whitelist of approved email addresses
        self.add_to_whitelist("pagett.jared@gmail.com")
        self.add_to_whitelist("jestes@ucsb.edu")
        self.add_to_whitelist("jpagett@ucsb.edu")
        self.add_to_whitelist("mbl@ucsb.edu")
        self.add_to_whitelist(self.email_handler.email_address)
        
        # Command handlers - maps keywords to handler functions
        self.add_command_handler(["sources","source","atoms"], self.handle_sources_command)
        self.add_command_handler(["als"], self.handle_als_command)
        self.add_command_handler(["preci", "precilaser"], self.handle_precilaser_command)
        self.add_command_handler(["all"], self.handle_all_command)

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
    """Main function to run the command controller"""
    controller = RemoteControl()
    controller.run_continuous()

if __name__ == "__main__":
    main()
