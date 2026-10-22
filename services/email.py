import smtplib
from email.message import EmailMessage

from core.config import get_settings


def send_officer_credentials(
    recipient: str,
    first_name: str,
    password: str,
) -> None:
    settings = get_settings()

    if not settings.smtp_host or not settings.smtp_username:
        raise RuntimeError("SMTP email settings are not configured")

    message = EmailMessage()
    message["Subject"] = "Your Vesper patrol account"
    message["From"] = settings.email_from or settings.smtp_username
    message["To"] = recipient

    message.set_content(
        f"""Hello {first_name},

Your Vesper patrol account has been created.

Login email: {recipient}
Temporary password: {password}

Please log in and change your password as soon as possible.
Do not share these credentials with anyone.

If you did not expect this email, contact your patrol coordinator.
"""
    )

    smtp_password = settings.smtp_password.get_secret_value()

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls()
        server.login(settings.smtp_username, smtp_password)
        server.send_message(message)


def send_password_reset_email(
    recipient: str,
    first_name: str,
    reset_token: str,
) -> None:
    settings = get_settings()

    if not settings.smtp_host or not settings.smtp_username:
        raise RuntimeError("SMTP email settings are not configured")

    reset_url = (
        f"{settings.frontend_url.rstrip('/')}/reset-password?token={reset_token}"
    )

    message = EmailMessage()
    message["Subject"] = "Reset your Vesper patrol password"
    message["From"] = settings.email_from or settings.smtp_username
    message["To"] = recipient

    message.set_content(
        f"""Hello {first_name},

You requested a password reset for your Vesper patrol account.

Use the link below to set a new password:
{reset_url}

This link expires in 15 minutes and can only be used once.
If you did not request this reset, you can safely ignore this email.
"""
    )

    smtp_password = settings.smtp_password.get_secret_value()

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls()
        server.login(settings.smtp_username, smtp_password)
        server.send_message(message)
