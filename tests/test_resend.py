
import resend

from core.config import get_settings


def _send_email(recipient: str, subject: str, text: str) -> None:
    settings = get_settings()
    api_key = settings.resend_api_key.get_secret_value()

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    resend.api_key = api_key

    resend.Emails.send(
        {
            "from": "Vesper <onboarding@resend.dev>",
            "to": [recipient],
            "subject": subject,
            "text": text,
        }
    )


def send_officer_credentials(
    recipient: str, first_name: str, password: str
) -> None:
    _send_email(
        recipient=recipient,
        subject="Your Vesper patrol account",
        text=(
            f"Hello {first_name},\n\n"
            "Your Vesper patrol account has been created.\n\n"
            f"Login email: {recipient}\n"
            f"Temporary password: {password}\n\n"
            "Please log in and change your password."
        ),
    )


def send_password_reset_email(
    recipient: str, first_name: str, reset_code: str
) -> None:
    _send_email(
        recipient=recipient,
        subject="Your Vesper password reset code",
        text=(
            f"Hello {first_name},\n\n"
            f"Your password reset code is: {reset_code}\n\n"
            "This code expires in 15 minutes."
        ),
    )
