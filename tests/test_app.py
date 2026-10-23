"""
tests/test_app.py – PyTest suite for the SuJob Flask application.

Tests cover:
  - Route accessibility (auth-gated vs public)
  - Login / signup / logout flows
  - Job search with mocked Adzuna API
  - Application submission
  - Job alert creation and deletion
  - Admin status update + Socket.IO emit
  - Worker helpers (email builder, Adzuna fetch mock)
  - Config values
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_instance():
    """Create a testable Flask app with a mock MySQL connection."""
    import sys
    import types

    # Stub out flask_mysqldb so we don't need a real MySQL server
    flask_mysqldb_mock = types.ModuleType('flask_mysqldb')
    class _MySQL:
        def __init__(self, app=None):
            self.connection = MagicMock()
        def init_app(self, app):
            pass
    flask_mysqldb_mock.MySQL = _MySQL
    sys.modules.setdefault('flask_mysqldb', flask_mysqldb_mock)

    # Stub out pika so RabbitMQ isn't needed
    pika_mock = types.ModuleType('pika')
    pika_mock.URLParameters = MagicMock()
    pika_mock.BlockingConnection = MagicMock()
    pika_mock.BasicProperties = MagicMock()
    pika_mock.exceptions = types.SimpleNamespace(AMQPConnectionError=Exception)
    sys.modules.setdefault('pika', pika_mock)

    from app import app
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


@pytest.fixture
def logged_in_client(app_instance):
    """Client with an active session (seeker role)."""
    with app_instance.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id']  = 1
            sess['username'] = 'testuser'
            sess['email']    = 'test@example.com'
            sess['role']     = 'seeker'
            sess['avatar']   = 'images/default-avatar.jpg'
        yield c


@pytest.fixture
def admin_client(app_instance):
    """Client with admin role."""
    with app_instance.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id']  = 99
            sess['username'] = 'admin'
            sess['email']    = 'admin@example.com'
            sess['role']     = 'admin'
            sess['avatar']   = 'images/default-avatar.jpg'
        yield c


# ---------------------------------------------------------------------------
# Helper: mock DictCursor
# ---------------------------------------------------------------------------

def make_cursor(rows=None, one=None):
    """Return a mock that behaves like a DictCursor."""
    cur = MagicMock()
    cur.fetchone.return_value = one
    cur.fetchall.return_value = rows or []
    return cur


# ---------------------------------------------------------------------------
# 1. Public routes
# ---------------------------------------------------------------------------

class TestPublicRoutes:
    def test_home_200(self, client):
        rv = client.get('/')
        assert rv.status_code == 200

    def test_login_page(self, client):
        rv = client.get('/login')
        assert rv.status_code == 200
        assert b'Sign In' in rv.data or b'Login' in rv.data

    def test_signup_page(self, client):
        rv = client.get('/signup')
        assert rv.status_code == 200

    def test_index_redirects_home(self, client):
        rv = client.get('/index', follow_redirects=False)
        assert rv.status_code == 302


# ---------------------------------------------------------------------------
# 2. Auth-gated routes redirect when not logged in
# ---------------------------------------------------------------------------

class TestAuthGating:
    @pytest.mark.parametrize('path', [
        '/jobs', '/dashboard', '/applications',
        '/alerts', '/profile', '/contact_us',
    ])
    def test_redirect_when_not_logged_in(self, client, path):
        rv = client.get(path, follow_redirects=False)
        assert rv.status_code in (301, 302)
        assert '/login' in rv.headers['Location']


# ---------------------------------------------------------------------------
# 3. Login flow
# ---------------------------------------------------------------------------

class TestLoginFlow:
    def test_invalid_credentials(self, app_instance):
        with app_instance.test_client() as c:
            with patch('app.get_cursor') as mock_cursor_fn:
                cur = make_cursor(one=None)
                mock_cursor_fn.return_value = cur
                rv = c.post('/login', data={
                    'email': 'wrong@example.com',
                    'password': 'badpass',
                }, follow_redirects=True)
                assert rv.status_code == 200
                assert b'Invalid' in rv.data

    def test_valid_login_redirects_to_dashboard(self, app_instance):
        from werkzeug.security import generate_password_hash
        with app_instance.test_client() as c:
            with patch('app.get_cursor') as mock_cursor_fn:
                cur = make_cursor(one={
                    'id': 1,
                    'username': 'alice',
                    'email': 'alice@example.com',
                    'avatar_path': None,
                    'role': 'seeker',
                    'password': generate_password_hash('secret'),
                })
                mock_cursor_fn.return_value = cur
                rv = c.post('/login', data={
                    'email': 'alice@example.com',
                    'password': 'secret',
                }, follow_redirects=False)
                assert rv.status_code == 302
                assert '/dashboard' in rv.headers['Location']


# ---------------------------------------------------------------------------
# 4. Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_clears_session(self, logged_in_client):
        rv = logged_in_client.get('/logout', follow_redirects=False)
        assert rv.status_code == 302
        with logged_in_client.session_transaction() as sess:
            assert 'user_id' not in sess


# ---------------------------------------------------------------------------
# 5. Jobs – Adzuna API mocked
# ---------------------------------------------------------------------------

MOCK_JOB = {
    'id': 'adzuna-abc-123',
    'title': 'Python Developer',
    'company': {'display_name': 'TechCorp'},
    'location': {'display_name': 'London'},
    'salary_min': 40000,
    'salary_max': 60000,
    'contract_type': 'permanent',
    'contract_time': 'full_time',
    'description': 'A great Python role.',
    'redirect_url': 'https://example.com/job/1',
    'created': '2025-01-15T10:00:00Z',
}


class TestJobs:
    def _mock_api(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'results': [MOCK_JOB], 'count': 1}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_jobs_page_renders(self, logged_in_client):
        with patch('app.get_cursor') as mc, \
             patch('requests.get') as mock_get:
            cur = make_cursor(rows=[])
            mc.return_value = cur
            mock_get.return_value = self._mock_api()
            rv = logged_in_client.get('/jobs')
            assert rv.status_code == 200
            assert b'Python Developer' in rv.data

    def test_jobs_with_filters(self, logged_in_client):
        with patch('app.get_cursor') as mc, \
             patch('requests.get') as mock_get:
            cur = make_cursor(rows=[])
            mc.return_value = cur
            mock_get.return_value = self._mock_api()
            rv = logged_in_client.get(
                '/jobs?what=python&where=london&salary_min=30000&contract_type=permanent'
            )
            assert rv.status_code == 200
            call_params = mock_get.call_args[1]['params']
            assert call_params['what'] == 'python'
            assert call_params['salary_min'] == '30000'

    def test_jobs_api_failure_shows_error(self, logged_in_client):
        with patch('app.get_cursor') as mc, \
             patch('requests.get') as mock_get:
            cur = make_cursor(rows=[])
            mc.return_value = cur
            mock_get.side_effect = Exception('Connection refused')
            rv = logged_in_client.get('/jobs')
            assert rv.status_code == 200
            assert b'Failed' in rv.data or b'error' in rv.data.lower()


# ---------------------------------------------------------------------------
# 6. Applications
# ---------------------------------------------------------------------------

class TestApplications:
    def test_my_applications_page(self, logged_in_client):
        with patch('app.get_cursor') as mc:
            mc.return_value = make_cursor(rows=[])
            rv = logged_in_client.get('/applications')
            assert rv.status_code == 200

    def test_apply_new_job(self, logged_in_client):
        with patch('app.get_cursor') as mc:
            # first call: check duplicate → None; second call: insert
            cur = MagicMock()
            cur.fetchone.return_value = None   # no duplicate
            mc.return_value = cur
            with patch('app.mysql') as mock_mysql:
                mock_mysql.connection = MagicMock()
                rv = logged_in_client.post('/apply/adzuna-abc-123', data={
                    'job_title': 'Python Developer',
                    'company':   'TechCorp',
                    'location':  'London',
                    'cover_letter': 'I am a great fit.',
                }, follow_redirects=False)
                assert rv.status_code == 302

    def test_apply_duplicate_redirects(self, logged_in_client):
        with patch('app.get_cursor') as mc:
            cur = make_cursor(one={'id': 5})   # already exists
            mc.return_value = cur
            rv = logged_in_client.post('/apply/adzuna-abc-123', data={
                'job_title': 'Python Developer',
                'company':   'TechCorp',
                'location':  'London',
            }, follow_redirects=False)
            assert rv.status_code == 302


# ---------------------------------------------------------------------------
# 7. Job Alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_alerts_page_get(self, logged_in_client):
        with patch('app.get_cursor') as mc:
            mc.return_value = make_cursor(rows=[])
            rv = logged_in_client.get('/alerts')
            assert rv.status_code == 200

    def test_create_alert(self, logged_in_client):
        with patch('app.get_cursor') as mc, \
             patch('app._publish_alert') as mock_pub, \
             patch('app.mysql') as mock_mysql:
            cur = MagicMock()
            cur.fetchone.return_value = {'email': 'test@example.com'}
            cur.fetchall.return_value = []
            mc.return_value = cur
            mock_mysql.connection = MagicMock()
            rv = logged_in_client.post('/alerts', data={
                'keyword':       'Flask Developer',
                'location':      'London',
                'salary_min':    '40000',
                'contract_type': 'permanent',
            }, follow_redirects=True)
            assert rv.status_code == 200
            mock_pub.assert_called_once()

    def test_delete_alert(self, logged_in_client):
        with patch('app.get_cursor') as mc, \
             patch('app.mysql') as mock_mysql:
            mc.return_value = make_cursor()
            mock_mysql.connection = MagicMock()
            rv = logged_in_client.post('/alerts/delete/7', follow_redirects=False)
            assert rv.status_code == 302


# ---------------------------------------------------------------------------
# 8. Admin status update
# ---------------------------------------------------------------------------

class TestAdmin:
    def test_admin_dashboard_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin', follow_redirects=False)
        assert rv.status_code == 302   # redirected away

    def test_admin_dashboard_accessible_to_admin(self, admin_client):
        with patch('app.get_cursor') as mc:
            mc.return_value = make_cursor(rows=[])
            rv = admin_client.get('/admin')
            assert rv.status_code == 200

    def test_update_status_emits_socketio(self, admin_client):
        with patch('app.get_cursor') as mc, \
             patch('app.mysql') as mock_mysql, \
             patch('app.socketio') as mock_sio:
            cur = MagicMock()
            cur.fetchone.return_value = {
                'user_id': 1,
                'job_title': 'Python Developer',
                'company': 'TechCorp',
            }
            mc.return_value = cur
            mock_mysql.connection = MagicMock()
            rv = admin_client.post('/admin/update_status/3', data={
                'status': 'interview'
            }, follow_redirects=False)
            assert rv.status_code == 302
            mock_sio.emit.assert_called_once()
            emit_args = mock_sio.emit.call_args
            assert emit_args[0][0] == 'status_update'
            assert emit_args[0][1]['new_status'] == 'interview'

    def test_invalid_status_rejected(self, admin_client):
        with patch('app.get_cursor') as mc:
            mc.return_value = make_cursor()
            rv = admin_client.post('/admin/update_status/3', data={
                'status': 'hacked'
            }, follow_redirects=True)
            assert rv.status_code == 200  # stays on page


# ---------------------------------------------------------------------------
# 9. API endpoint
# ---------------------------------------------------------------------------

class TestApiApplications:
    def test_api_returns_json(self, logged_in_client):
        from datetime import datetime
        with patch('app.get_cursor') as mc:
            mc.return_value = make_cursor(rows=[{
                'id': 1,
                'job_title': 'Dev',
                'company': 'Co',
                'location': 'London',
                'status': 'applied',
                'applied_at': datetime(2025, 1, 1),
            }])
            rv = logged_in_client.get('/api/applications')
            assert rv.status_code == 200
            data = json.loads(rv.data)
            assert isinstance(data, list)
            assert data[0]['job_title'] == 'Dev'


# ---------------------------------------------------------------------------
# 10. Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_has_required_keys(self):
        from config import Config
        assert hasattr(Config, 'MYSQL_HOST')
        assert hasattr(Config, 'ADZUNA_APP_ID')
        assert hasattr(Config, 'RABBITMQ_URL')
        assert hasattr(Config, 'ALERT_QUEUE')
        assert hasattr(Config, 'MAIL_SERVER')

    def test_alert_queue_name(self):
        from config import Config
        assert Config.ALERT_QUEUE == 'job_alerts'


# ---------------------------------------------------------------------------
# 11. Worker helpers (no real RabbitMQ or SMTP needed)
# ---------------------------------------------------------------------------

class TestWorkerHelpers:
    def test_build_email_html_contains_keyword(self):
        from worker import build_email_html
        jobs = [{
            'title': 'Django Dev',
            'company': {'display_name': 'ACME'},
            'location': {'display_name': 'Leeds'},
            'redirect_url': 'https://example.com',
            'salary_min': 30000,
            'salary_max': 50000,
        }]
        html = build_email_html(jobs, 'django')
        assert 'django' in html.lower()
        assert 'Django Dev' in html
        assert 'ACME' in html

    def test_fetch_matching_jobs_mocked(self):
        from worker import fetch_matching_jobs
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'results': [MOCK_JOB]}
        mock_resp.raise_for_status.return_value = None
        with patch('requests.get', return_value=mock_resp):
            results = fetch_matching_jobs('python', 'london')
            assert len(results) == 1
            assert results[0]['title'] == 'Python Developer'

    def test_fetch_matching_jobs_api_error_returns_empty(self):
        from worker import fetch_matching_jobs
        with patch('requests.get', side_effect=Exception('Timeout')):
            results = fetch_matching_jobs('python')
            assert results == []

    def test_send_email_skips_when_no_username(self):
        """send_email should be a no-op when MAIL_USERNAME is not set."""
        import worker as w
        original = w.MAIL_USERNAME
        w.MAIL_USERNAME = ''
        # Should not raise
        w.send_email('user@example.com', 'Test', '<html>hi</html>')
        w.MAIL_USERNAME = original


# ---------------------------------------------------------------------------
# 12. Schema SQL sanity check
# ---------------------------------------------------------------------------

class TestSchemaSql:
    def test_schema_file_exists(self):
        import os
        assert os.path.exists('schema.sql')

    def test_schema_contains_tables(self):
        with open('schema.sql') as f:
            content = f.read().lower()
        for table in ['users', 'job_alerts', 'jobs_cache', 'applications']:
            assert f'create table if not exists {table}' in content, \
                f"Table '{table}' not found in schema.sql"

    def test_schema_has_indexes(self):
        with open('schema.sql') as f:
            content = f.read().lower()
        assert 'index' in content or 'create index' in content
