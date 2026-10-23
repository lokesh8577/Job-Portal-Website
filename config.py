import os

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # MySQL
    MYSQL_HOST     = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER     = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.environ.get('MYSQL_DB', 'job_portal')

    # File uploads
    UPLOAD_FOLDER     = 'static/uploads/avatars'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024   # 2 MB

    # Adzuna API
    ADZUNA_APP_ID  = os.environ.get('ADZUNA_APP_ID',  '99fec87a')
    ADZUNA_APP_KEY = os.environ.get('ADZUNA_APP_KEY', '8905bef4907c1064be1687c95af949bb')
    ADZUNA_BASE    = 'https://api.adzuna.com/v1/api/jobs/gb/search/1'

    # RabbitMQ
    RABBITMQ_URL   = os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
    ALERT_QUEUE    = 'job_alerts'

    # Email (SMTP – set real values via env vars)
    MAIL_SERVER   = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
    MAIL_PORT     = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS  = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_FROM     = os.environ.get('MAIL_FROM', 'noreply@sujob.example.com')
