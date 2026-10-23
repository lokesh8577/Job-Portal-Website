"""
app.py – Job Portal (Flask + MySQL + Socket.IO + RabbitMQ alerts)
"""

import os
import json
import requests
from functools import wraps
from datetime import datetime

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

try:
    from flask_mysqldb import MySQL
except ImportError:
    # Pure-Python MySQL client wrapper using PyMySQL
    class MySQL:
        def __init__(self, app=None):
            self.app = app

        @property
        def connection(self):
            from flask import g
            if 'db' not in g:
                import pymysql
                import pymysql.cursors
                g.db = pymysql.connect(
                    host=app.config.get('MYSQL_HOST', 'localhost'),
                    user=app.config.get('MYSQL_USER', 'root'),
                    password=app.config.get('MYSQL_PASSWORD', ''),
                    database=app.config.get('MYSQL_DB', 'job_portal'),
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False
                )
            return g.db

from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

# Socket.IO with eventlet/gevent-compatible async mode
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

mysql = MySQL(app)

@app.teardown_appcontext
def close_db_connection(exception=None):
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    )


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated


def get_cursor():
    """Return a fresh DictCursor."""
    try:
        import MySQLdb.cursors
        return mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    except Exception:
        try:
            import pymysql.cursors
            return mysql.connection.cursor(pymysql.cursors.DictCursor)
        except Exception:
            return mysql.connection.cursor()


def _publish_alert(payload: dict):
    """
    Publish a job-alert message to RabbitMQ (best-effort).
    Falls back gracefully if RabbitMQ is not running.
    """
    try:
        import pika
        params = pika.URLParameters(app.config['RABBITMQ_URL'])
        conn   = pika.BlockingConnection(params)
        ch     = conn.channel()
        ch.queue_declare(queue=app.config['ALERT_QUEUE'], durable=True)
        ch.basic_publish(
            exchange='',
            routing_key=app.config['ALERT_QUEUE'],
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        conn.close()
    except Exception as exc:
        app.logger.warning("RabbitMQ publish failed (is it running?): %s", exc)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/index')
def index():
    return redirect(url_for('home'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        cur  = get_cursor()
        cur.execute(
            "SELECT id, username, email, avatar_path, role, password "
            "FROM users WHERE email = %s",
            (email,)
        )
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user['password'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['email']    = user['email']
            session['role']     = user['role']
            session['avatar']   = user['avatar_path'] or 'images/default-avatar.jpg'
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('password', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        avatar   = request.files.get('avatar')

        # Save avatar
        avatar_path = None
        if avatar and allowed_file(avatar.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filename    = secure_filename(avatar.filename)
            full_path   = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            avatar.save(full_path)
            avatar_path = full_path.replace('static/', '')

        cur = get_cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            flash('An account with that email already exists.', 'warning')
            return render_template('signup.html')

        hashed = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, password, avatar_path) "
            "VALUES (%s, %s, %s, %s)",
            (username, email, hashed, avatar_path)
        )
        mysql.connection.commit()
        cur.close()

        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    cur = get_cursor()

    # Recent applications
    cur.execute(
        "SELECT * FROM applications WHERE user_id = %s "
        "ORDER BY applied_at DESC LIMIT 5",
        (uid,)
    )
    recent_apps = cur.fetchall()

    # Alert count
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM job_alerts WHERE user_id = %s AND is_active = 1",
        (uid,)
    )
    alert_count = cur.fetchone()['cnt']
    cur.close()

    return render_template('dashboard.html',
                           recent_apps=recent_apps,
                           alert_count=alert_count)


# ---------------------------------------------------------------------------
# Jobs – search via Adzuna + cache results
# ---------------------------------------------------------------------------

@app.route('/jobs', methods=['GET'])
@login_required
def jobs():
    what          = request.args.get('what', '').strip()
    where         = request.args.get('where', '').strip()
    salary_min    = request.args.get('salary_min', '').strip()
    contract_type = request.args.get('contract_type', '').strip()
    page          = int(request.args.get('page', 1))

    jobs_list = []
    total     = 0
    error     = None

    try:
        params = {
            'app_id':           app.config['ADZUNA_APP_ID'],
            'app_key':          app.config['ADZUNA_APP_KEY'],
            'results_per_page': 20,
        }
        if what:          params['what']          = what
        if where:         params['where']         = where
        if salary_min:    params['salary_min']    = salary_min
        if contract_type: params['contract_type'] = contract_type

        url = app.config['ADZUNA_BASE'].replace('/1', f'/{page}')
        resp = requests.get(url, params=params,
                            headers={'User-Agent': 'SuJob/1.0'}, timeout=10)
        resp.raise_for_status()
        data      = resp.json()
        jobs_list = data.get('results', [])
        total     = data.get('count', 0)

        # Cache results in MySQL (upsert)
        cur = get_cursor()
        for j in jobs_list:
            cur.execute("""
                INSERT INTO jobs_cache
                    (adzuna_id, title, company, location,
                     salary_min, salary_max, contract_type, contract_time,
                     description, redirect_url, posted_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    title=VALUES(title), cached_at=NOW()
            """, (
                j.get('id'),
                j.get('title'),
                j.get('company', {}).get('display_name'),
                j.get('location', {}).get('display_name'),
                j.get('salary_min'),
                j.get('salary_max'),
                j.get('contract_type'),
                j.get('contract_time'),
                j.get('description', '')[:4000],
                j.get('redirect_url'),
                j.get('created'),
            ))
        mysql.connection.commit()
        cur.close()

    except Exception as exc:
        app.logger.error("Adzuna API error: %s", exc)
        error = "Failed to fetch jobs. Please try again later."

    # Applied job IDs for current user
    applied_ids = set()
    if session.get('user_id'):
        cur = get_cursor()
        cur.execute(
            "SELECT adzuna_id FROM applications WHERE user_id = %s",
            (session['user_id'],)
        )
        applied_ids = {r['adzuna_id'] for r in cur.fetchall()}
        cur.close()

    return render_template('jobs.html',
                           jobs=jobs_list,
                           applied_ids=applied_ids,
                           search_what=what,
                           search_where=where,
                           search_salary=salary_min,
                           selected_contract_type=contract_type,
                           page=page,
                           total=total,
                           error=error)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

@app.route('/apply/<adzuna_id>', methods=['POST'])
@login_required
def apply(adzuna_id):
    uid          = session['user_id']
    cover_letter = request.form.get('cover_letter', '').strip()
    job_title    = request.form.get('job_title', '')
    company      = request.form.get('company', '')
    location     = request.form.get('location', '')

    cur = get_cursor()
    cur.execute(
        "SELECT id FROM applications WHERE user_id=%s AND adzuna_id=%s",
        (uid, adzuna_id)
    )
    if cur.fetchone():
        flash('You have already applied for this job.', 'info')
        cur.close()
        return redirect(url_for('jobs'))

    cur.execute("""
        INSERT INTO applications
            (user_id, adzuna_id, job_title, company, location, cover_letter)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (uid, adzuna_id, job_title, company, location, cover_letter))
    mysql.connection.commit()
    cur.close()

    flash(f'Applied for "{job_title}" successfully!', 'success')
    return redirect(url_for('my_applications'))


@app.route('/applications')
@login_required
def my_applications():
    uid = session['user_id']
    cur = get_cursor()
    cur.execute(
        "SELECT * FROM applications WHERE user_id=%s ORDER BY applied_at DESC",
        (uid,)
    )
    apps = cur.fetchall()
    cur.close()
    return render_template('applications.html', applications=apps)


# ---------------------------------------------------------------------------
# Job Alerts
# ---------------------------------------------------------------------------

@app.route('/alerts', methods=['GET', 'POST'])
@login_required
def alerts():
    uid = session['user_id']
    cur = get_cursor()

    if request.method == 'POST':
        keyword       = request.form.get('keyword', '').strip()
        location      = request.form.get('location', '').strip()
        salary_min    = request.form.get('salary_min') or None
        contract_type = request.form.get('contract_type', '').strip() or None

        cur.execute("""
            INSERT INTO job_alerts
                (user_id, keyword, location, salary_min, contract_type)
            VALUES (%s,%s,%s,%s,%s)
        """, (uid, keyword, location, salary_min, contract_type))
        mysql.connection.commit()
        flash('Job alert created!', 'success')

        # Publish to RabbitMQ for async processing
        cur.execute(
            "SELECT email FROM users WHERE id=%s", (uid,)
        )
        user_email = cur.fetchone()['email']
        _publish_alert({
            'user_id':       uid,
            'email':         user_email,
            'keyword':       keyword,
            'location':      location,
            'salary_min':    salary_min,
            'contract_type': contract_type,
        })

    cur.execute(
        "SELECT * FROM job_alerts WHERE user_id=%s ORDER BY created_at DESC",
        (uid,)
    )
    user_alerts = cur.fetchall()
    cur.close()
    return render_template('alerts.html', alerts=user_alerts)


@app.route('/alerts/delete/<int:alert_id>', methods=['POST'])
@login_required
def delete_alert(alert_id):
    uid = session['user_id']
    cur = get_cursor()
    cur.execute(
        "DELETE FROM job_alerts WHERE id=%s AND user_id=%s",
        (alert_id, uid)
    )
    mysql.connection.commit()
    cur.close()
    flash('Alert deleted.', 'info')
    return redirect(url_for('alerts'))


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    uid = session['user_id']
    cur = get_cursor()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        avatar   = request.files.get('avatar')
        avatar_path = None

        if avatar and allowed_file(avatar.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filename   = secure_filename(avatar.filename)
            full_path  = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            avatar.save(full_path)
            avatar_path = full_path.replace('static/', '')
            cur.execute(
                "UPDATE users SET username=%s, avatar_path=%s WHERE id=%s",
                (username, avatar_path, uid)
            )
            session['avatar'] = avatar_path
        else:
            cur.execute(
                "UPDATE users SET username=%s WHERE id=%s",
                (username, uid)
            )

        mysql.connection.commit()
        session['username'] = username
        flash('Profile updated.', 'success')

    cur.execute(
        "SELECT id, username, email, avatar_path, role, created_at "
        "FROM users WHERE id=%s",
        (uid,)
    )
    user = cur.fetchone()
    cur.close()
    return render_template('profile.html', user=user)


# ---------------------------------------------------------------------------
# Admin – update application status (triggers Socket.IO)
# ---------------------------------------------------------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    cur = get_cursor()
    cur.execute("""
        SELECT a.*, u.username, u.email
        FROM applications a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.applied_at DESC
    """)
    all_apps = cur.fetchall()
    cur.close()
    return render_template('admin.html', applications=all_apps)


@app.route('/admin/update_status/<int:app_id>', methods=['POST'])
@admin_required
def update_status(app_id):
    new_status = request.form.get('status')
    valid = ('applied', 'reviewing', 'interview', 'offered', 'rejected')
    if new_status not in valid:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_dashboard'))

    cur = get_cursor()
    cur.execute(
        "UPDATE applications SET status=%s WHERE id=%s",
        (new_status, app_id)
    )
    mysql.connection.commit()

    # Fetch user_id for Socket.IO room
    cur.execute(
        "SELECT user_id, job_title, company FROM applications WHERE id=%s",
        (app_id,)
    )
    row = cur.fetchone()
    cur.close()

    if row:
        # Emit real-time event to the applicant's private room
        socketio.emit(
            'status_update',
            {
                'application_id': app_id,
                'job_title':      row['job_title'],
                'company':        row['company'],
                'new_status':     new_status,
            },
            room=f"user_{row['user_id']}",
        )
        flash('Status updated and user notified.', 'success')

    return redirect(url_for('admin_dashboard'))


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

@app.route('/contact_us')
@login_required
def contact_us():
    return render_template('contact_us.html')


# ---------------------------------------------------------------------------
# Socket.IO events
# ---------------------------------------------------------------------------

@socketio.on('join')
def on_join(data):
    """Client calls join({user_id: N}) to subscribe to their status updates."""
    user_id = data.get('user_id')
    if user_id and str(user_id) == str(session.get('user_id')):
        join_room(f"user_{user_id}")
        emit('joined', {'room': f"user_{user_id}"})


# ---------------------------------------------------------------------------
# API – application status (JSON, used by tests)
# ---------------------------------------------------------------------------

@app.route('/api/applications', methods=['GET'])
@login_required
def api_applications():
    uid = session['user_id']
    cur = get_cursor()
    cur.execute(
        "SELECT id, job_title, company, location, status, applied_at "
        "FROM applications WHERE user_id=%s ORDER BY applied_at DESC",
        (uid,)
    )
    apps = cur.fetchall()
    cur.close()
    # Convert datetimes to strings
    for a in apps:
        a['applied_at'] = str(a['applied_at'])
    return jsonify(apps)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    socketio.run(app, debug=True, host='0.0.0.0', port=3000)
