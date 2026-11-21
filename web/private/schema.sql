CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(190) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','editor','viewer') NOT NULL DEFAULT 'admin',
  status ENUM('active','pending','disabled') NOT NULL DEFAULT 'active',
  auth_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS auth_tokens (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  token_hash CHAR(64) NOT NULL UNIQUE,
  purpose ENUM('invite','reset') NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_auth_tokens_user (user_id),
  CONSTRAINT fk_auth_token_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS auth_attempts (
  selector CHAR(64) NOT NULL PRIMARY KEY,
  failures INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS photos (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  stored_name VARCHAR(80) NOT NULL UNIQUE,
  original_name VARCHAR(255) NOT NULL,
  sha256 CHAR(64) NOT NULL,
  dhash CHAR(16) NOT NULL DEFAULT '',
  color_sig CHAR(6) NOT NULL DEFAULT '',
  mime VARCHAR(32) NOT NULL,
  file_size BIGINT UNSIGNED NOT NULL,
  width INT UNSIGNED NOT NULL,
  height INT UNSIGNED NOT NULL,
  camera VARCHAR(255) NOT NULL DEFAULT '',
  taken_at VARCHAR(64) NOT NULL DEFAULT '',
  location VARCHAR(150) NOT NULL DEFAULT '',
  attraction VARCHAR(190) NOT NULL DEFAULT '',
  activities TEXT NULL,
  source_folder VARCHAR(500) NOT NULL DEFAULT '',
  source_url VARCHAR(1000) NOT NULL DEFAULT '',
  photographer VARCHAR(255) NOT NULL DEFAULT '',
  copyright_text VARCHAR(1000) NOT NULL DEFAULT '',
  license VARCHAR(255) NOT NULL DEFAULT '',
  rights_status VARCHAR(32) NOT NULL DEFAULT 'Unknown',
  ai_status VARCHAR(32) NOT NULL DEFAULT 'not analyzed',
  ai_note TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_location (location),
  KEY idx_attraction (attraction),
  KEY idx_created (created_at),
  KEY idx_sha (sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- File manager v0.3. Existing installs use drive_migrate() instead.
CREATE TABLE IF NOT EXISTS folders (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(190) NOT NULL,
  parent_id BIGINT UNSIGNED NULL,
  created_by BIGINT UNSIGNED NULL,
  deleted_at DATETIME NULL,
  trash_batch CHAR(32) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_folder_parent (parent_id),
  KEY idx_folder_deleted (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- API v1 tables. Existing installs get these through migrate_api.php.
CREATE TABLE IF NOT EXISTS api_tokens (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  token_hash CHAR(64) NOT NULL UNIQUE,
  label VARCHAR(80) NOT NULL,
  scope ENUM('read','write') NOT NULL,
  auth_version INT UNSIGNED NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  last_used_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_api_token_user (user_id),
  KEY idx_api_token_expiry (expires_at),
  CONSTRAINT fk_api_token_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS api_rate_limits (
  token_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  hits INT UNSIGNED NOT NULL DEFAULT 0,
  window_started DATETIME NOT NULL,
  CONSTRAINT fk_api_rate_token FOREIGN KEY (token_id) REFERENCES api_tokens(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
