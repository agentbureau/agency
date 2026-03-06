import smtplib
from email.message import EmailMessage


def send_notification(cfg: dict, to: str, subject: str, body: str) -> None:
    """Send a plain-text notification email using client SMTP config."""
    ec = cfg["email"]
    msg = EmailMessage()
    msg["From"] = ec["sender_address"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as s:
        s.starttls()
        s.login(ec["smtp_username"], ec["smtp_password"])
        s.send_message(msg)
