import os
import smtplib
import ssl
from email.message import EmailMessage


def _bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_smtp_config() -> tuple[str, int, str | None, str | None, str, bool, bool]:
    host = os.getenv("SMTP_HOST")
    from_addr = os.getenv("SMTP_USER")
    if not host or not from_addr:
        raise ValueError("SMTP_HOST and SMTP_USER must be set")

    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    use_tls = _bool_env(os.getenv("SMTP_USE_TLS"), default=True)
    use_ssl = _bool_env(os.getenv("SMTP_USE_SSL"), default=False)

    return host, port, username, password, from_addr, use_tls, use_ssl


def send_email(to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    host, port, username, password, from_addr, use_tls, use_ssl = _get_smtp_config()

    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
        return

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            context = ssl.create_default_context()
            server.starttls(context=context)
        if username and password:
            server.login(username, password)
        server.send_message(message)
