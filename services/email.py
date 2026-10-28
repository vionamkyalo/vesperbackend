import resend

from core.config import get_settings


def _send_email(
    recipient: str,
    subject: str,
    text: str,
) -> None:
    settings = get_settings()
    api_key = settings.resend_api_key

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    if hasattr(api_key, "get_secret_value"):
        api_key = api_key.get_secret_value()

    resend.api_key = api_key

    resend.Emails.send(
        {
            "from": settings.email_from,
            "to": [recipient],
            "subject": subject,
            "text": text,
        }
    )


def send_officer_credentials(
    recipient: str,
    first_name: str,
    password: str,
) -> None:
    _send_email(
        recipient=recipient,
        subject="Your Vesper patrol account",
        text=f"""Hello {first_name},

Your Vesper patrol account has been created.

Login email: {recipient}
Temporary password: {password}

Please log in and change your password as soon as possible.
Do not share these credentials with anyone.

If you did not expect this email, contact your patrol coordinator.
""",
    )


def send_password_reset_email(
    recipient: str,
    first_name: str,
    reset_code: str,
) -> None:
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
