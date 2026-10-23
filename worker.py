"""
worker.py – RabbitMQ consumer that processes job-alert notifications.

Run separately:
    python worker.py

The worker:
1. Subscribes to the 'job_alerts' queue.
2. For each message it calls the Adzuna API to find matching jobs.
3. Sends an email summary to the user.
4. Logs the notification in MySQL.
"""

import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pika
import requests
try:
    import MySQLdb
except ImportError:
    try:
        import pymysql as MySQLdb
    except ImportError:
        MySQLdb = None

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [WORKER] %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (read from environment, same as Flask app)
# ---------------------------------------------------------------------------
RABBITMQ_URL   = os.environ.get('RABBITMQ_URL',   'amqp://guest:guest@localhost:5672/')
ALERT_QUEUE    = os.environ.get('ALERT_QUEUE',    'job_alerts')
ADZUNA_APP_ID  = os.environ.get('ADZUNA_APP_ID',  '99fec87a')
ADZUNA_APP_KEY = os.environ.get('ADZUNA_APP_KEY', '8905bef4907c1064be1687c95af949bb')
ADZUNA_BASE    = 'https://api.adzuna.com/v1/api/jobs/gb/search/1'

MYSQL_HOST     = os.environ.get('MYSQL_HOST',     'localhost')
MYSQL_USER     = os.environ.get('MYSQL_USER',     'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DB       = os.environ.get('MYSQL_DB',       'job_portal')

MAIL_SERVER    = os.environ.get('MAIL_SERVER',    'smtp.gmail.com')
MAIL_PORT      = int(os.environ.get('MAIL_PORT',  587))
MAIL_USERNAME  = os.environ.get('MAIL_USERNAME',  '')
MAIL_PASSWORD  = os.environ.get('MAIL_PASSWORD',  '')
MAIL_FROM      = os.environ.get('MAIL_FROM',      'noreply@sujob.example.com')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    if MySQLdb is None:
        raise RuntimeError("Neither MySQLdb nor PyMySQL is installed.")
    return MySQLdb.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB,
        charset='utf8mb4',
    )


def fetch_matching_jobs(keyword, location=None, salary_min=None, contract_type=None):
    """Call Adzuna and return a list of job dicts."""
    params = {
        'app_id':  ADZUNA_APP_ID,
        'app_key': ADZUNA_APP_KEY,
        'results_per_page': 5,
        'what':    keyword,
    }
    if location:      params['where']         = location
    if salary_min:    params['salary_min']    = salary_min
    if contract_type: params['contract_type'] = contract_type

    try:
        resp = requests.get(ADZUNA_BASE, params=params,
                            headers={'User-Agent': 'SuJob-Worker/1.0'}, timeout=10)
        resp.raise_for_status()
        return resp.json().get('results', [])
    except Exception as exc:
        log.error("Adzuna fetch error: %s", exc)
        return []


def send_email(to_email: str, subject: str, html_body: str):
    """Send an HTML email via configured SMTP. No-op if credentials not set."""
    if not MAIL_USERNAME:
        log.info("MAIL_USERNAME not set – skipping email to %s", to_email)
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = MAIL_FROM
    msg['To']      = to_email
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
            smtp.sendmail(MAIL_FROM, to_email, msg.as_string())
        log.info("Email sent to %s", to_email)
    except Exception as exc:
        log.error("Email send failed: %s", exc)


def build_email_html(jobs, keyword):
    rows = ""
    for j in jobs:
        title   = j.get('title', 'N/A')
        company = j.get('company', {}).get('display_name', 'N/A')
        loc     = j.get('location', {}).get('display_name', 'N/A')
        url     = j.get('redirect_url', '#')
        sal_min = j.get('salary_min')
        sal_max = j.get('salary_max')
        salary  = f"£{sal_min:,.0f} – £{sal_max:,.0f}" if sal_min and sal_max else "Not disclosed"
        rows += f"""
        <tr>
          <td><a href="{url}">{title}</a></td>
          <td>{company}</td>
          <td>{loc}</td>
          <td>{salary}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:sans-serif">
    <h2 style="color:#3D52A0">🔔 New Jobs Matching "{keyword}"</h2>
    <p>Here are the latest matches for your job alert:</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
      <tr style="background:#3D52A0;color:#fff">
        <th>Title</th><th>Company</th><th>Location</th><th>Salary</th>
      </tr>
      {rows}
    </table>
    <p style="color:#888;font-size:12px;margin-top:20px">
      You received this because you set up a job alert on SuJob.
    </p>
    </body></html>
    """


def log_notification(db, alert_id):
    cur = db.cursor()
    cur.execute(
        "INSERT INTO alert_notifications (alert_id) VALUES (%s)",
        (alert_id,)
    )
    db.commit()
    cur.close()


# ---------------------------------------------------------------------------
# Message callback
# ---------------------------------------------------------------------------

def process_message(ch, method, _props, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        log.error("Bad JSON payload: %s", body)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    log.info("Processing alert for user %s (%s)",
             payload.get('user_id'), payload.get('email'))

    keyword       = payload.get('keyword', '')
    location      = payload.get('location')
    salary_min    = payload.get('salary_min')
    contract_type = payload.get('contract_type')
    email         = payload.get('email')

    jobs = fetch_matching_jobs(keyword, location, salary_min, contract_type)

    if jobs and email:
        html = build_email_html(jobs, keyword)
        send_email(email, f'SuJob Alert: new jobs matching "{keyword}"', html)

    # Find the latest alert id for this user + keyword to log
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT id FROM job_alerts WHERE user_id=%s AND keyword=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (payload.get('user_id'), keyword)
        )
        row = cur.fetchone()
        cur.close()
        if row:
            log_notification(db, row[0])
        db.close()
    except Exception as exc:
        log.error("DB logging error: %s", exc)

    ch.basic_ack(delivery_tag=method.delivery_tag)
    log.info("Done processing alert for %s", email)


# ---------------------------------------------------------------------------
# Main loop with reconnect
# ---------------------------------------------------------------------------

def start_worker():
    while True:
        try:
            log.info("Connecting to RabbitMQ at %s …", RABBITMQ_URL)
            params = pika.URLParameters(RABBITMQ_URL)
            conn   = pika.BlockingConnection(params)
            ch     = conn.channel()
            ch.queue_declare(queue=ALERT_QUEUE, durable=True)
            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue=ALERT_QUEUE, on_message_callback=process_message)
            log.info("Worker ready. Waiting for messages on '%s' …", ALERT_QUEUE)
            ch.start_consuming()
        except pika.exceptions.AMQPConnectionError as exc:
            log.warning("RabbitMQ unavailable: %s. Retrying in 5 s…", exc)
            time.sleep(5)
        except KeyboardInterrupt:
            log.info("Worker stopped.")
            break
        except Exception as exc:
            log.error("Unexpected error: %s. Retrying in 5 s…", exc)
            time.sleep(5)


if __name__ == '__main__':
    start_worker()
