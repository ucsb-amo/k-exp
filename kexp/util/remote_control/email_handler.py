import imaplib
import email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import re
import time

logger = logging.getLogger(__name__)

EMAIL_ADDRESS = "kcontrol.ucsb@gmail.com"
GVOICE_NUMBER = "8053642409"
EMAIL_PASSWORD = "riqs amym ocpe mize"
SLACK_EMAIL = "general-aaaaahzr4dmblwquygpk47q6le@weldlab.slack.com"
CHECK_EMAIL_INTERVAL = 10

class EmailHandler:
    """
    Handles all email-related functionality including IMAP, SMTP, and email processing
    """
    
    def __init__(self, process_commands_method, parse_commands_method,
                  email_whitelist=[], phone_whitelist=[]):
        
        self.process_commands = process_commands_method
        self.parse_commands = parse_commands_method
        
        self.email_address = EMAIL_ADDRESS
        self.email_password = EMAIL_PASSWORD
        self.whitelist = email_whitelist
        self.phone_whitelist = phone_whitelist
        self.slack_channel = SLACK_EMAIL
        
        # Email server configuration
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587

    def print_instructions(self):
        gvnumber = f"{GVOICE_NUMBER[:3]}-{GVOICE_NUMBER[3:6]}-{GVOICE_NUMBER[6:]}"
        logger.info(f"Email check success. Send commands to {gvnumber} or to {EMAIL_ADDRESS}.")
    
    def connect_to_email(self):
        """Connect to Gmail IMAP server"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            self.print_instructions()
            return mail
        except Exception as e:
            logger.error(f"Failed to connect to email server: {e}")
            return None
    
    def is_sender_whitelisted(self, sender_email):
        """Check if sender email is in the whitelist"""
        sender_email = sender_email.lower().strip()
        
        # Special handling for Google Voice emails
        if sender_email.endswith("@txt.voice.google.com"):
            # Extract the first two parts (Google Voice number and phone number)
            # Format: 1{gvoice_number}.1{phone_number}.{variable_part}@txt.voice.google.com
            match = re.match(r'^(1\d{10}\.1\d{10})\.[^.]+@txt\.voice\.google\.com$', sender_email)
            if match:
                gvoice_prefix = match.group(1)
                # Check if any whitelisted email starts with this prefix
                for whitelisted_addr in self.whitelist:
                    if whitelisted_addr.lower().startswith(gvoice_prefix.lower() + ".") and whitelisted_addr.lower().endswith("@txt.voice.google.com"):
                        return True
        
        # Standard email check
        return sender_email in [addr.lower() for addr in self.whitelist]
    
    def extract_sender_email(self, from_field):
        """Extract email address from the From field"""
        # Handle formats like "Name <email@domain.com>" or just "email@domain.com"
        match = re.search(r'<([^>]+)>', from_field)
        if match:
            return match.group(1)
        else:
            return from_field.strip()
    
    def send_slack_notification(self, message):
        """
        Send a notification message to the Slack channel
        """
        if not self.slack_channel:
            logger.warning("No Slack channel configured")
            return False
            
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = self.slack_channel
            msg['Subject'] = 'K-Exp Control Notification'
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_address, self.email_password)
            
            server.sendmail(self.email_address, self.slack_channel, msg.as_string())
            server.quit()
            
            logger.info("Slack notification sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    def send_response_email(self, recipient, subject, body):
        """Send a response email to the sender"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = recipient
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_address, self.email_password)
            
            server.sendmail(self.email_address, recipient, msg.as_string())
            server.quit()
            
            logger.info(f"Response email sent to {recipient}")
            return True
        except Exception as e:
            logger.error(f"Failed to send response email: {e}")
            return False
    
    def extract_email_body(self, msg):
        """Extract email body from message"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8')
                    break
        else:
            body = msg.get_payload(decode=True).decode('utf-8')
        return body
    
    def process_email(self, msg):
        """
        Process a single email message
        
        Args:
            msg: Email message object
            command_processor: Function that takes (commands, sender_email) and returns results
        """
        try:
            # Extract sender information
            from_field = msg.get('From', '')
            sender_email = self.extract_sender_email(from_field)

            # Check if sender is whitelisted
            if not self.is_sender_whitelisted(sender_email):
                logger.warning(f"Email from non-whitelisted sender: {sender_email}")
                return
            else:
                sender = self.log_whitelisted_sender(sender_email)
            
            # Extract email body
            body = self.extract_email_body(msg)
            
            # Process commands using the provided command processor
            commands = self.parse_commands(body)
            if not commands:
                logger.info("No valid commands found in email")
                return
            
            self.process_commands(sender,commands)
            
        except Exception as e:
            logger.error(f"Error processing email: {e}")
        
    def log_whitelisted_sender(self,sender_email):
        if sender_email.endswith("@txt.voice.google.com"):
            # Extract phone number from Google Voice email address
            match = re.search(r'\.1(\d{10})\.', sender_email)
            if match:
                phone_number = match.group(1)
                logger.info(f"Received text from whitelisted phone: {phone_number}")
                sender = phone_number
            else:
                logger.info(f"Received text from whitelisted Google Voice email: {sender_email}")
                sender = sender_email
        else:
            logger.info(f"Received email from whitelisted address: {sender_email}")
            sender = sender_email
        return sender
    
    def check_emails(self):
        """
        Check for new emails and process them
        
        Args:
            command_processor: Function that takes (email_body, sender_email) and returns results
        """
        mail = self.connect_to_email()
        if not mail:
            return
        
        try:
            # Select the inbox
            mail.select("INBOX")
            # Search for unseen emails
            status, messages = mail.search(None, "UNSEEN")
            if status == "OK":
                email_ids = messages[0].split()
                for email_id in email_ids:
                    # Fetch the email
                    status, msg_data = mail.fetch(email_id, "(RFC822)")
                    if status == "OK":
                        # Parse the email
                        msg = email.message_from_bytes(msg_data[0][1])
                        # Process the email
                        self.process_email(msg)
                        # Mark as read
                        mail.store(email_id, '+FLAGS', '\\Seen')
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error checking emails: {e}")
            try:
                mail.logout()
            except:
                pass
    
    def add_phone_to_whitelist(self, phone_number):
        """
        Add a phone number to the whitelist and generate corresponding Google Voice email
        
        Args:
            phone_number (str): 10-digit phone number without delimiters
        """
        # Remove any delimiters and validate
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        
        if len(clean_phone) != 10:
            logger.error(f"Invalid phone number: {phone_number}. Must be 10 digits.")
            return False
        
        if clean_phone not in self.phone_whitelist:
            self.phone_whitelist.append(clean_phone)
            
            # Generate and add Google Voice email (note: third part may vary, but whitelist check handles this)
            google_voice_email = f"1{GVOICE_NUMBER}.1{clean_phone}.placeholder@txt.voice.google.com"
            if google_voice_email not in self.whitelist:
                self.whitelist.append(google_voice_email)
                logger.info(f"Added phone {clean_phone} to whitelist")
            else:
                logger.info(f"Phone {clean_phone} added to whitelist (Google Voice email already existed)")
            
            return True
        else:
            logger.info(f"Phone number {clean_phone} already in whitelist")
            return True
    
    def add_to_whitelist(self, email_or_phone):
        """
        Add an email address or phone number to the whitelist
        
        Args:
            email_or_phone (str): Email address or 10-digit phone number
        """
        # Check if it's a phone number (only digits, 10 characters)
        clean_input = re.sub(r'[^\d]', '', email_or_phone)
        if len(clean_input) == 10 and clean_input == email_or_phone.replace('-', '').replace('(', '').replace(')', '').replace(' ', ''):
            # It's a phone number
            return self.add_phone_to_whitelist(email_or_phone)
        else:
            # It's an email address
            if email_or_phone.lower() not in [addr.lower() for addr in self.whitelist]:
                self.whitelist.append(email_or_phone)
                logger.info(f"Added {email_or_phone} to email whitelist")
                return True
            else:
                logger.info(f"{email_or_phone} already in email whitelist")
                return True
    
    def get_phone_whitelist(self):
        """Return the current phone number whitelist"""
        return self.phone_whitelist.copy()
    
    def get_email_whitelist(self):
        """Return the current email whitelist"""
        return self.whitelist.copy()
    
    def should_ignore_command(self, command, value):
        """
        Check if a command should be ignored (filtered out without logging)
        Returns True if the command should be ignored
        """
        # Commands to ignore (Google Voice auto-generated content)
        ignored_commands = {
            '<https': ['//voice.google.com>', '//productforums.google.com/forum/#!forum/voice>', '//voice.google.com/settings#messaging>.', '//voice.google.com> help center'],
            '<https://support.google.com/voice#topic': ['1707989> help forum'],
            'google': ['llc'],
            'your account <https': ['//voice.google.com> help center']
        }
        
        return command in ignored_commands and value in ignored_commands.get(command, [])

    def run_continuous(self, check_interval=CHECK_EMAIL_INTERVAL):
        """
        Run the controller continuously, checking for new emails
        at specified intervals (in seconds)
        """
        logger.info(f"Starting command controller with {check_interval}s check interval.\n")
        
        while True:
            try:
                self.check_emails()
                time.sleep(check_interval)
            except KeyboardInterrupt:
                logger.info("Command controller stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(check_interval)