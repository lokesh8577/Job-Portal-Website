# SuJob - Full-Stack Job Portal Platform

[![Python CI/CD](https://github.com/your-username/Job_portel/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/Job_portel/actions)

A full-stack, enterprise-grade job portal platform built with **Python**, **Flask**, **MySQL**, **RabbitMQ**, **Socket.IO**, and **GitHub Actions**.

---

## 🌟 Key Features

1. **Normalized MySQL Schemas & Search Optimization**
   - Normalized database schema with `users`, `job_alerts`, `jobs_cache`, `applications`, and `alert_notifications` tables.
   - B-tree indexed filter columns (`title`, `location`, `salary_min`, `contract_type`, `posted_at`) ensuring high-throughput search queries across 10K+ cached and live listings.
   - Automatic caching and upserting of external job listings to avoid redundant external network round-trips.

2. **Adzuna API Job Aggregation & Filtering**
   - Real-time job search integrated with the Adzuna API.
   - Granular multi-parameter filtering: keywords, location, minimum salary, and contract type (Permanent, Contract, Part-Time).
   - In-app job application submission with custom cover letters.

3. **Asynchronous Job Alerts with RabbitMQ**
   - Decoupled, asynchronous notification architecture using RabbitMQ background workers (`worker.py`).
   - Keeps user-facing HTTP request cycles fast by offloading job query matching, HTML email rendering, and SMTP delivery to background workers.
   - Dedicated message durability, connection retry logic, and delivery acknowledgments (`basic_ack`).

4. **Real-Time Application Status Updates with Socket.IO**
   - Bi-directional WebSockets via Flask-SocketIO.
   - Recruiters/admins can update application review statuses (`applied`, `reviewing`, `interview`, `offered`, `rejected`) from the Admin Dashboard.
   - Instant room-based push notifications (`user_<id>`) delivered directly to the candidate's browser without page refreshes.

5. **Automated Testing & GitHub Actions CI/CD**
   - Complete PyTest test suite (`tests/test_app.py`) with 36 unit and integration test cases covering routes, authentication, Adzuna API mocking, database operations, alerts, Socket.IO emits, and worker helpers.
   - GitHub Actions workflow running on every push and pull request against Python 3.13.

---

## 📁 Project Architecture

```
Job_portel/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI/CD pipeline
├── static/
│   ├── css/
│   │   ├── styles.css           # Modern theme styling
│   │   └── sign_in_and_sign_up.css
│   ├── images/                  # UI assets and illustrations
│   ├── js/
│   │   └── scripts.js           # Client interactions
│   └── uploads/avatars/         # User uploaded profile pictures
├── templates/
│   ├── base.html                # Master layout with Socket.IO listener
│   ├── index.html               # Landing page with hero & features
│   ├── jobs.html                # Job search, filters & apply modal
│   ├── dashboard.html           # User dashboard with stats & quick actions
│   ├── applications.html        # Real-time application tracker
│   ├── alerts.html              # Job alerts management
│   ├── admin.html               # Recruiter application status management
│   ├── profile.html             # Profile edit page
│   ├── login.html               # Sign in page
│   ├── signup.html              # Registration page
│   └── contact_us.html          # Contact form
├── tests/
│   ├── __init__.py
│   └── test_app.py              # PyTest test suite (36 tests)
├── app.py                       # Main Flask & Socket.IO application
├── config.py                    # Centralized environment configuration
├── worker.py                    # RabbitMQ consumer worker for email alerts
├── schema.sql                   # Normalized MySQL database schema
├── requirements.txt             # Project dependencies
└── README.md
```

---

## 🛠️ Getting Started

### 1. Prerequisites
- Python 3.10+
- MySQL Server
- RabbitMQ Server (optional for local mock testing)

### 2. Installation

Clone the repository and install dependencies:
```bash
git clone https://github.com/your-username/Job_portel.git
cd Job_portel

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Setup

Create the MySQL database and run the schema:
```bash
mysql -u root -p < schema.sql
```

### 4. Configuration

Environment variables can be configured via `.env` or system environment (defaults provided in [config.py](file:///Users/sonu/Documents/Job_portel/config.py)):
- `MYSQL_HOST`: MySQL host (default: `localhost`)
- `MYSQL_USER`: MySQL user (default: `root`)
- `MYSQL_PASSWORD`: MySQL password (default: `""`)
- `MYSQL_DB`: Database name (`job_portal`)
- `RABBITMQ_URL`: AMQP connection URL (default: `amqp://guest:guest@localhost:5672/`)
- `ADZUNA_APP_ID`: Your Adzuna App ID
- `ADZUNA_APP_KEY`: Your Adzuna App Key
- `MAIL_SERVER` / `MAIL_USERNAME` / `MAIL_PASSWORD`: SMTP settings for alert emails

---

## 🚀 Running the Platform

### Start the Flask Web & Socket.IO Application
```bash
python3 app.py
```
Access the application at `http://localhost:3000`.

### Start the RabbitMQ Background Alert Worker
In a separate terminal:
```bash
python3 worker.py
```

---

## 🧪 Running Tests

Run the full automated PyTest test suite:
```bash
pytest tests/ -v
```

All 36 tests execute in under a second with isolated mocks for database, AMQP, and third-party APIs.
