from kexp.util.remote_control.command_handler import CommandHandler
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RemoteControl(CommandHandler):
    def __init__(self):
        super().__init__()

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
        
        # Command handlers - maps keywords to handler functions
        self.add_command_handler(["sources","source","atoms"], self.handle_sources_command)

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
        
def main():
    """Main function to run the command controller"""
    controller = RemoteControl()
    controller.run_continuous()

if __name__ == "__main__":
    main()
