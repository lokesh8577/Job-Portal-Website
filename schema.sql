-- ============================================================
-- Job Portal – Normalized MySQL Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS job_portal
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE job_portal;

-- ----------------------------------------------------------
-- 1. Users
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id           INT          NOT NULL AUTO_INCREMENT,
    username     VARCHAR(80)  NOT NULL,
    email        VARCHAR(120) NOT NULL UNIQUE,
    password     VARCHAR(255) NOT NULL,          -- store hashed passwords in production
    role         ENUM('seeker','admin') NOT NULL DEFAULT 'seeker',
    avatar_path  VARCHAR(255),
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_users_email (email)
) ENGINE=InnoDB;

-- ----------------------------------------------------------
-- 2. Job Alerts (what the user wants to be notified about)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_alerts (
    id            INT          NOT NULL AUTO_INCREMENT,
    user_id       INT          NOT NULL,
    keyword       VARCHAR(120) NOT NULL,
    location      VARCHAR(120),
    salary_min    INT          UNSIGNED,
    contract_type VARCHAR(30),
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_alerts_user   (user_id),
    INDEX idx_alerts_active (is_active),
    CONSTRAINT fk_alerts_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------
-- 3. Cached Jobs (pulled from Adzuna to avoid repeat API hits)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs_cache (
    id            INT           NOT NULL AUTO_INCREMENT,
    adzuna_id     VARCHAR(64)   NOT NULL UNIQUE,
    title         VARCHAR(255)  NOT NULL,
    company       VARCHAR(120),
    location      VARCHAR(120),
    salary_min    DECIMAL(12,2),
    salary_max    DECIMAL(12,2),
    contract_type VARCHAR(30),
    contract_time VARCHAR(30),
    description   TEXT,
    redirect_url  VARCHAR(512),
    posted_at     DATETIME,
    cached_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_jobs_title    (title),
    INDEX idx_jobs_location (location),
    INDEX idx_jobs_sal_min  (salary_min),
    INDEX idx_jobs_contract (contract_type),
    INDEX idx_jobs_posted   (posted_at)
) ENGINE=InnoDB;

-- ----------------------------------------------------------
-- 4. Applications
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS applications (
    id           INT          NOT NULL AUTO_INCREMENT,
    user_id      INT          NOT NULL,
    adzuna_id    VARCHAR(64)  NOT NULL,           -- links to jobs_cache.adzuna_id
    job_title    VARCHAR(255) NOT NULL,
    company      VARCHAR(120),
    location     VARCHAR(120),
    cover_letter TEXT,
    status       ENUM('applied','reviewing','interview','offered','rejected')
                              NOT NULL DEFAULT 'applied',
    applied_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_user_job (user_id, adzuna_id),
    INDEX idx_apps_user   (user_id),
    INDEX idx_apps_status (status),
    INDEX idx_apps_date   (applied_at),
    CONSTRAINT fk_apps_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------
-- 5. Alert Notification Log
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_notifications (
    id         INT      NOT NULL AUTO_INCREMENT,
    alert_id   INT      NOT NULL,
    sent_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_notif_alert (alert_id),
    CONSTRAINT fk_notif_alert FOREIGN KEY (alert_id)
        REFERENCES job_alerts(id) ON DELETE CASCADE
) ENGINE=InnoDB;
