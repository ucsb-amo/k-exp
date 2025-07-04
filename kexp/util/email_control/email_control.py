from command_handler import CommandHandler
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmailControl(CommandHandler):
    def __init__(self):
        super().__init__()

        # Whitelist of approved phone numbers (10 digits, no delimiters)
        self.add_to_whitelist("9165834119")
        
        # Whitelist of approved email addresses
        self.add_to_whitelist("pagett.jared@gmail.com")
        self.add_to_whitelist("jestes@ucsb.edu")
        self.add_to_whitelist("jpagett@ucsb.edu")
        self.add_to_whitelist("mbl@gmail.com")
        
        # Command handlers - maps keywords to handler functions
        self.add_command_handler("sources", self.handle_sources_command)

    def handle_sources_command(self, value):
        """
        Handle the 'sources' command to turn sources on or off
        """
        try:
            on_values = ["on", "1", "true"]
            off_values = ["off", "0", "false"]

            value_lower = value.strip().lower()
            if value_lower in on_values:
                self.ethernet_relay.source_on()
                return "Sources successfully turned ON"
            
            elif value_lower in off_values:
                self.ethernet_relay.source_off()
                return "Sources successfully turned OFF"
            else:
                logger.warning(f"Invalid sources command value: {value}")
                return f"Invalid sources command. Use 'sources = on' or 'sources = off'"
            
        except Exception as e:
            logger.error(f"Error controlling sources: {e}")
            return f"Error controlling sources: {e}"
        
def main():
    """Main function to run the command controller"""
    controller = EmailControl()
    controller.run_continuous()

if __name__ == "__main__":
    main()
