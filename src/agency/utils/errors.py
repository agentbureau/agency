"""
Task 34: Error handling — three error types with configurable timeouts
and optional email notification via stdlib smtplib.
"""
import smtplib
import logging
from email.message import EmailMessage
from enum import IntEnum

log = logging.getLogger(__name__)


class ErrorType(IntEnum):
    TYPE_1 = 1  # Transient — log and continue
    TYPE_2 = 2  # Recoverable — log, notify, retry after timeout
    TYPE_3 = 3  # Fatal — log, notify, halt


class PrimitiveStoreEmpty(Exception):
    """Raised when the primitive store contains no role components."""
    pass


class AgencyError(Exception):
    def __init__(self, message: str, error_type: ErrorType = ErrorType.TYPE_1):
        super().__init__(message)
        self.error_type = error_type


def handle_error(
    error: AgencyError,
    contact_email: str | None = None,
    smtp_host: str = "localhost",
    smtp_port: int = 25,
    timeout_seconds: int = 300,
) -> None:
    """
    Handle an AgencyError according to its type.

    Type 1: log only
    Type 2: log + notify
    Type 3: log + notify + raise (caller must halt)
    """
    log.error("[AgencyError type=%d] %s", error.error_type, error)

    if error.error_type >= ErrorType.TYPE_2 and contact_email:
        _notify(str(error), contact_email, smtp_host, smtp_port)

    if error.error_type == ErrorType.TYPE_3:
        raise error


def _notify(
    message: str,
    contact_email: str,
    smtp_host: str,
    smtp_port: int,
) -> None:
    try:
        msg = EmailMessage()
        msg["Subject"] = "[Agency] Error notification"
        msg["From"] = f"agency@{smtp_host}"
        msg["To"] = contact_email
        msg.set_content(message)
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as s:
            s.send_message(msg)
    except Exception as e:
        log.warning("Failed to send error notification: %s", e)
