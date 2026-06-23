import os
import logging
import smtplib
from email.message import EmailMessage

from job_cd.core.interfaces import EmailSenderStrategy
from job_cd.core.models import EmailDraft


class SmtpEmailSender(EmailSenderStrategy):
    """
    Sends emails using standard SMTP.
    """
    def __init__(self):
        self.smtp_server = os.environ.get('SMTP_SERVER', "smtp.gmail.com")
        raw_port = os.environ.get('SMTP_PORT', "587")
        try:
            self.smtp_port = int(raw_port)
        except (ValueError, TypeError):
            self.smtp_port = 587
        self.smtp_username = os.environ.get('SMTP_USERNAME')
        self.smtp_password = os.environ.get('SMTP_PASSWORD')

        if not self.smtp_username or not self.smtp_password:
            logging.error("SMTP credentials not set")
            raise ValueError("SMTP credentials not set")

    def _connect(self):
        if self.smtp_port == 465:
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
        else:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.ehlo()
            server.starttls()
        return server

    def send_email(self, draft: EmailDraft):
        logging.info(f"Sending email to {draft.recipient_email} with subject: {draft.subject}")
        msg = EmailMessage()
        msg['Subject'] = draft.subject
        msg['From'] = draft.sender_email
        msg['To'] = draft.recipient_email

        msg.set_content(draft.body, subtype='html')
        try:
            server = self._connect()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()

            logging.info(f"Successfully sent email to {draft.recipient_email}")
            return True

        except Exception as e:
            logging.error(f"Failed to send email to {draft.recipient_email}: {e}")
            return False
