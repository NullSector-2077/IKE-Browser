#!/usr/bin/env python3
"""Send the owner an e-mail from a workflow (1.1.19, the owner's request; no AI here).

    send-mail.py --subject TEXT --body-file FILE

The addresses and the password are never in the repository (it is public):
they come from the repository's secrets, given to the step as environment
variables, and nothing of them is printed:

    MAIL_USERNAME      the Gmail address that sends
    MAIL_APP_PASSWORD  an app password of that Gmail account (not its password)
    MAIL_TO            the addresses that receive, separated by commas

Without them it says so and exits with 3 (0 when sent): a mail is a notice,
the workflow decides whether that matters. Sent with Gmail's SMTP over TLS (smtp.gmail.com:465),
tried three times.
"""

import argparse
import os
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path

HOST, PORT = "smtp.gmail.com", 465


def recipients(text):
    return [a.strip() for a in (text or "").replace(";", ",").split(",") if "@" in a.strip()]


def build(sender, to, subject, body):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send(subject, body, env=os.environ, smtp=smtplib.SMTP_SSL, sleep=time.sleep):
    """True when sent; False when not configured or not sent (said why, no secret)."""
    user, password, to = env.get("MAIL_USERNAME", ""), env.get("MAIL_APP_PASSWORD", ""), recipients(env.get("MAIL_TO"))
    if not (user and password and to):
        print("::notice::e-mail not configured (secrets MAIL_USERNAME, MAIL_APP_PASSWORD, MAIL_TO): not sent")
        return False
    msg = build(user, to, subject, body)
    for attempt in range(3):
        try:
            with smtp(HOST, PORT, context=ssl.create_default_context(), timeout=30) as s:
                s.login(user, password)
                s.send_message(msg)
            print("e-mail sent to %d address(es)" % len(to))
            return True
        except Exception as e:                  # never the message of the error: it may echo a secret
            print("::warning::e-mail not sent (%s), attempt %d of 3" % (type(e).__name__, attempt + 1))
            sleep(20 * (attempt + 1))
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body-file", required=True)
    a = ap.parse_args(argv)
    # 0 sent, 3 not sent (not configured or refused): the caller decides
    return 0 if send(a.subject, Path(a.body_file).read_text("utf-8", "replace")) else 3


if __name__ == "__main__":
    sys.exit(main())
