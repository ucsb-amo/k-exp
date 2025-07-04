import time
import re
import logging
from kexp.control.ethernet_relay import EthernetRelay
from email_handler import EmailHandler

logger = logging.getLogger(__name__)

class CommandHandler:
    """
    Main command controller that handles command parsing and execution
    """
    
    def __init__(self):
        # Email configuration
        self.email_handler = EmailHandler(self.process_commands, self.parse_commands)
        
        # Initialize ethernet relay
        self.ethernet_relay = EthernetRelay()

    def run_continuous(self):
        """
        Run the controller continuously, checking for new emails
        at specified intervals (in seconds)
        """
        self.email_handler.run_continuous()
    
    def parse_commands(self, email_body):
        """
        Parse email body for commands in format 'keyword delimiter value'
        Supports delimiters: ' ', '=', ':'
        Space padding is ignored for '=' and ':', but not for single space
        Returns dictionary of commands found
        """
        commands = {}
        
        # Split by lines and process each line
        lines = email_body.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try different delimiters
            command_found = False
            
            # First try '=' and ':' with optional space padding
            for delimiter in ['=', ':']:
                if delimiter in line:
                    parts = line.split(delimiter, 1)
                    if len(parts) == 2:
                        keyword = parts[0].strip()
                        value = parts[1].strip()
                        if keyword and value:
                            # Check if this command should be ignored
                            if not self.email_handler.should_ignore_command(keyword.lower(), value.lower()):
                                commands[keyword.lower()] = value.lower()
                            command_found = True
                            break
            
            # If not found with '=' or ':', try single space delimiter (no padding)
            if not command_found and ' ' in line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    keyword = parts[0].strip()
                    value = parts[1].strip()
                    # Only accept if both parts are single words (no spaces)
                    if keyword and value and ' ' not in keyword and ' ' not in value:
                        # Check if this command should be ignored
                        if not self.email_handler.should_ignore_command(keyword.lower(), value.lower()):
                            commands[keyword.lower()] = value.lower()
                        command_found = True
            
            # Also try regex pattern for more flexible matching
            if not command_found:
                pattern = r'(\w+)\s*[=:]\s*(\w+)'
                matches = re.findall(pattern, line, re.IGNORECASE)
                for keyword, value in matches:
                    # Check if this command should be ignored
                    if not self.email_handler.should_ignore_command(keyword.lower(), value.lower()):
                        commands[keyword.lower()] = value.lower()
        
        return commands

    def process_commands(self, commands):
        """
        Process commands from email body
        Returns list of results or None if no commands found
        """
        
        results = []
        for keyword, value in commands.items():
            if keyword in self.command_handlers:
                result = self.command_handlers[keyword](value)
                results.append(f"{keyword}: {value} -- {result}")
            else:
                logger.warning(f"Unknown command: {keyword}")
                results.append(f"{keyword}: Unknown command")
        logger.info(f"Processed commands:\n" + "\n     ".join(results))
    
    def add_command_handler(self, keyword, handler_function):
        """
        Add a new command handler for easy extension
        
        Args:
            keyword (str): The command keyword to match
            handler_function (callable): Function that takes (value, sender_email) and returns result string
        """
        if not hasattr(self, 'command_handlers'):
            self.command_handlers = {}
        self.command_handlers[keyword] = handler_function
        logger.info(f"Added command handler for keyword: {keyword}")
    
    def send_slack_notification(self, message):
        """Send a notification message to the Slack channel"""
        return self.email_handler.send_slack_notification(message)
    
    def add_to_whitelist(self, email_or_phone):
        """Add an email address or phone number to the whitelist"""
        return self.email_handler.add_to_whitelist(email_or_phone)