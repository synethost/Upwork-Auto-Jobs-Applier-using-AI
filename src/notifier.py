import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from colorama import Fore, Style, init

init(autoreset=True)


def send_run_summary(job_title: str, scraped: int, applied_jobs: list):
    """
    Send an HTML email summarising the run.

    applied_jobs: list of dicts — title, link, score, submitted (bool)
    Silently skips if NOTIFY_EMAIL / SMTP_USER / SMTP_PASSWORD are not set.
    """
    notify_email = os.getenv("NOTIFY_EMAIL", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not all([notify_email, smtp_user, smtp_password]):
        return

    count = len(applied_jobs)
    subject = f"Upwork Bot: applied to {count} job(s) for '{job_title}'"

    rows = ""
    for job in applied_jobs:
        status = "&#10003; Submitted" if job.get("submitted") else "&#128190; Saved locally"
        color = "#14a800" if job.get("submitted") else "#888"
        rows += (
            f'<tr>'
            f'<td style="padding:8px;border:1px solid #ddd;text-align:center">{job.get("score","?")}/10</td>'
            f'<td style="padding:8px;border:1px solid #ddd">'
            f'<a href="{job.get("link","#")}">{job.get("title","N/A")}</a></td>'
            f'<td style="padding:8px;border:1px solid #ddd;color:{color}">{status}</td>'
            f'</tr>'
        )

    body = f"""
<html><body style="font-family:Arial,sans-serif;max-width:760px;margin:0 auto;color:#333">
  <h2 style="color:#14a800">Upwork Auto-Applier — Run Summary</h2>
  <table style="border-collapse:collapse;margin-bottom:16px">
    <tr><td style="padding:4px 12px 4px 0"><strong>Time</strong></td>
        <td>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
    <tr><td style="padding:4px 12px 4px 0"><strong>Search</strong></td>
        <td>{job_title}</td></tr>
    <tr><td style="padding:4px 12px 4px 0"><strong>Scraped</strong></td>
        <td>{scraped} jobs</td></tr>
    <tr><td style="padding:4px 12px 4px 0"><strong>Applied</strong></td>
        <td>{count} jobs</td></tr>
  </table>

  <table style="border-collapse:collapse;width:100%">
    <thead>
      <tr style="background:#14a800;color:#fff">
        <th style="padding:8px">Score</th>
        <th style="padding:8px;text-align:left">Job</th>
        <th style="padding:8px">Status</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <p style="color:#aaa;font-size:12px;margin-top:24px">Sent by Upwork Auto-Applier</p>
</body></html>
"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = notify_email
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, notify_email, msg.as_string())

        print(Fore.GREEN + f"Email summary sent to {notify_email}\n" + Style.RESET_ALL)
    except Exception as e:
        print(Fore.YELLOW + f"Email notification failed: {e}\n" + Style.RESET_ALL)
