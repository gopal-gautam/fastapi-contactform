import os
from abc import ABC, abstractmethod

import requests


class MailServiceError(Exception):
    pass


class MailService(ABC):
    @abstractmethod
    def send_contact_email(self, name: str, email: str, subject: str, message: str) -> None:
        pass


class SendGridMailService(MailService):
    def __init__(self, api_key: str, to_email: str, from_email: str | None = None) -> None:
        self.api_key = api_key
        self.to_email = to_email
        self.from_email = from_email or to_email

    def send_contact_email(self, name: str, email: str, subject: str, message: str) -> None:
        if not self.api_key or not self.to_email:
            raise MailServiceError("Missing SendGrid configuration")

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "personalizations": [
                {
                    "to": [{"email": self.to_email}],
                    "subject": f"Contact Form: {subject}",
                }
            ],
            "from": {"email": self.from_email},
            "reply_to": {"email": email},
            "content": [
                {
                    "type": "text/plain",
                    "value": (
                        f"Name: {name}\n"
                        f"Email: {email}\n"
                        f"Subject: {subject}\n\n"
                        f"Message:\n{message}"
                    ),
                }
            ],
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code >= 300:
            raise MailServiceError(f"SendGrid error: {resp.status_code} {resp.text}")


class MailjetMailService(MailService):
    def __init__(self, api_key: str, api_secret: str, to_email: str, from_email: str | None = None) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.to_email = to_email
        self.from_email = from_email or to_email

    def send_contact_email(self, name: str, email: str, subject: str, message: str) -> None:
        if not self.api_key or not self.api_secret or not self.to_email:
            raise MailServiceError("Missing Mailjet configuration")

        url = "https://api.mailjet.com/v3.1/send"
        payload = {
            "Messages": [
                {
                    "From": {"Email": self.from_email, "Name": "Contact Form"},
                    "To": [{"Email": self.to_email}],
                    "Subject": f"Contact Form: {subject}",
                    "TextPart": (
                        f"Name: {name}\n"
                        f"Email: {email}\n"
                        f"Subject: {subject}\n\n"
                        f"Message:\n{message}"
                    ),
                    "ReplyTo": {"Email": email},
                }
            ]
        }

        resp = requests.post(url, auth=(self.api_key, self.api_secret), json=payload, timeout=10)
        if resp.status_code >= 300:
            raise MailServiceError(f"Mailjet error: {resp.status_code} {resp.text}")


def validate_mail_service_config() -> None:
    provider = os.getenv("MAIL_PROVIDER", "mailjet").strip().lower()
    required = ["TO_EMAIL"]

    if provider == "sendgrid":
        required.append("SENDGRID_API_KEY")
    elif provider == "mailjet":
        required.extend(["MAILJET_API_KEY", "MAILJET_API_SECRET"])
    else:
        raise MailServiceError(
            f"Unsupported MAIL_PROVIDER: {provider}. Supported values are 'mailjet' and 'sendgrid'."
        )

    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise MailServiceError(
            f"Missing required environment variables for provider '{provider}': {', '.join(missing)}"
        )


def get_mail_service() -> MailService:
    provider = os.getenv("MAIL_PROVIDER", "mailjet").strip().lower()

    to_email = os.getenv("TO_EMAIL", "")
    from_email = os.getenv("FROM_EMAIL", "")

    if provider == "sendgrid":
        return SendGridMailService(
            api_key=os.getenv("SENDGRID_API_KEY", ""),
            to_email=to_email,
            from_email=from_email or None,
        )

    if provider == "mailjet":
        return MailjetMailService(
            api_key=os.getenv("MAILJET_API_KEY", ""),
            api_secret=os.getenv("MAILJET_API_SECRET", ""),
            to_email=to_email,
            from_email=from_email or None,
        )

    raise MailServiceError(f"Unsupported MAIL_PROVIDER: {provider}")
