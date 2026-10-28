import os
import resend
from dotenv import load_dotenv

load_dotenv(".env", override=True)


def test_resend_sends_email():
    api_key = os.getenv("RESEND_API_KEY")
    assert api_key, "RESEND_API_KEY is missing"

    resend.api_key = api_key

    result = resend.Emails.send(
        {
            "from": "Vesper <onboarding@resend.dev>",
            "to": ["delivered@resend.dev"],
            "subject": "Vesper Resend integration test",
            "text": "Vesper successfully sent this test email.",
        }
    )

    assert result is not None
