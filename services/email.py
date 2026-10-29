import smtplib
from email.message import EmailMessage

from core.config import get_settings


def _send_email(recipient: str, subject: str, text: str) -> None:
    settings = get_settings()
    password = settings.smtp_password.get_secret_value()

    if not settings.smtp_username or not password:
        raise RuntimeError("SMTP_USERNAME / SMTP_PASSWORD are not configured")

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_username, password)
        server.send_message(message)


def send_officer_credentials(recipient: str, first_name: str, password: str) -> None:
    _send_email(
        recipient=recipient,
        subject="Your Vesper patrol account",
        text=f"""Hello {first_name},

Your Vesper patrol account has been created.

Login email: {recipient}
Password: {password}

Please log in and Do not share these credentials with anyone.

If you did not expect this email, contact your patrol coordinator.
""",
    )


def send_password_reset_email(recipient: str, first_name: str, reset_code: str) -> None:
    _send_email(
        recipient=recipient,
        subject="Your Vesper password reset code",
        text=f"""Hello {first_name},

You requested a password reset for your Vesper account.

Your six-digit verification code is:

{reset_code}

This code expires in 15 minutes.

Enter this code in the Vesper app to reset your password.
If you did not request this, you can ignore this email.
""",
    )
