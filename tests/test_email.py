from types import SimpleNamespace

import pytest
from pydantic import SecretStr

import services.email as email_service


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        self.username = username

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def fake_settings(username="team@test.local", password="app-pass"):
    return SimpleNamespace(
        smtp_host="smtp.test.local",
        smtp_port=587,
        smtp_username=username,
        smtp_password=SecretStr(password),
        email_from="Vesper <team@test.local>",
    )


@pytest.fixture(autouse=True)
def patch_smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)


def test_reset_email_contains_code(monkeypatch):
    monkeypatch.setattr(email_service, "get_settings", fake_settings)

    email_service.send_password_reset_email("officer@test.local", "Tendai", "123456")

    message = FakeSMTP.sent[0]
    assert message["To"] == "officer@test.local"
    assert message["From"] == "Vesper <team@test.local>"
    assert "123456" in message.get_content()


def test_officer_credentials_email(monkeypatch):
    monkeypatch.setattr(email_service, "get_settings", fake_settings)

    email_service.send_officer_credentials(
        "officer@test.local", "Tendai", "Temp-Pass-1"
    )

    message = FakeSMTP.sent[0]
    assert message["Subject"] == "Your Vesper patrol account"
    assert "Temp-Pass-1" in message.get_content()


def test_missing_smtp_settings_raises(monkeypatch):
    monkeypatch.setattr(
        email_service, "get_settings", lambda: fake_settings(password="")
    )

    with pytest.raises(RuntimeError):
        email_service.send_password_reset_email(
            "officer@test.local", "Tendai", "123456"
        )
    assert FakeSMTP.sent == []
