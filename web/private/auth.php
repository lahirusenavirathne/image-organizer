<?php
declare(strict_types=1);
require_once __DIR__.'/bootstrap.php';

const AUTH_IDLE_SECONDS = 1800;
const AUTH_ABSOLUTE_SECONDS = 43200;
const AUTH_PASSWORD_MIN_LENGTH = 14;
const AUTH_PASSWORD_MAX_BYTES = 72; // Avoid silent bcrypt truncation on hosts without Argon2.

/** Upgrade an existing one-admin installation without losing its account. */
function auth_migrate(PDO $db, bool $force=false): void {
    static $ready = false;
    if (!$force && ($ready || is_file(private_path('auth-v2-ready')))) return;
    // A filesystem lock prevents concurrent first-visit ALTER TABLE attempts on shared hosting.
    $lock = $force ? null : fopen(private_path('auth-migrate.lock'), 'c');
    if (!$force && (!$lock || !flock($lock, LOCK_EX))) throw new RuntimeException('Cannot lock authentication upgrade');
    try {
    if (!$force && is_file(private_path('auth-v2-ready'))) {$ready=true;return;}
    $columns = $db->query('SHOW COLUMNS FROM users')->fetchAll(PDO::FETCH_COLUMN);
    if (!in_array('role', $columns, true)) {
        $db->exec("ALTER TABLE users ADD COLUMN role ENUM('admin','editor','viewer') NOT NULL DEFAULT 'admin'");
    }
    if (!in_array('status', $columns, true)) {
        $db->exec("ALTER TABLE users ADD COLUMN status ENUM('active','pending','disabled') NOT NULL DEFAULT 'active'");
    }
    if (!in_array('auth_version', $columns, true)) {
        $db->exec('ALTER TABLE users ADD COLUMN auth_version INT UNSIGNED NOT NULL DEFAULT 1');
    }
    $db->exec("CREATE TABLE IF NOT EXISTS auth_tokens (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT UNSIGNED NOT NULL,
        token_hash CHAR(64) NOT NULL UNIQUE,
        purpose ENUM('invite','reset') NOT NULL,
        expires_at DATETIME NOT NULL,
        used_at DATETIME NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_auth_tokens_user (user_id),
        CONSTRAINT fk_auth_token_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
    $db->exec("CREATE TABLE IF NOT EXISTS auth_attempts (
        selector CHAR(64) NOT NULL PRIMARY KEY,
        failures INT UNSIGNED NOT NULL DEFAULT 0,
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
    if (!$force) {
        $tmp=private_path('auth-v2-ready.tmp');
        if (file_put_contents($tmp,"ready\n",LOCK_EX)===false || !rename($tmp,private_path('auth-v2-ready'))) {
            throw new RuntimeException('Could not record authentication migration');
        }
        @chmod(private_path('auth-v2-ready'),0600);
    }
    $ready = true;
    } finally {
        if ($lock) {flock($lock,LOCK_UN);fclose($lock);}
    }
}

function auth_normalize_email(mixed $email): string {
    if (!is_string($email)) return '';
    $email = strtolower(trim($email));
    return strlen($email) <= 190 && filter_var($email, FILTER_VALIDATE_EMAIL) ? $email : '';
}
function auth_validate_password(string $password, string $confirmation): void {
    if (strlen($password) < AUTH_PASSWORD_MIN_LENGTH || strlen($password) > AUTH_PASSWORD_MAX_BYTES) {
        throw new RuntimeException('Use a password with at least 14 characters (maximum 72 bytes).');
    }
    if (!hash_equals($password, $confirmation)) throw new RuntimeException('The password confirmation does not match.');
}
function auth_hash_password(string $password): string {
    return password_hash($password, PASSWORD_DEFAULT);
}
function auth_role_level(string $role): int { return ['viewer'=>1, 'editor'=>2, 'admin'=>3][$role] ?? 0; }
function auth_role_allowed(string $actual, string $minimum): bool {
    return auth_role_level($actual) >= auth_role_level($minimum) && auth_role_level($minimum) > 0;
}
function auth_ip_key(): string {
    $remote = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
    return hash('sha256', 'ip:'.$remote);
}
function auth_email_key(string $email): string { return hash('sha256', 'email:'.$email); }
function auth_limited(PDO $db, string $email): bool {
    foreach ([[auth_ip_key(),30], [auth_email_key($email),10]] as [$key,$limit]) {
        $query = $db->prepare('SELECT failures FROM auth_attempts WHERE selector=? AND updated_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 15 MINUTE)');
        $query->execute([$key]);
        if ((int)$query->fetchColumn() >= $limit) return true;
    }
    return false;
}
function auth_note_failure(PDO $db, string $email): void {
    $statement=$db->prepare("INSERT INTO auth_attempts(selector,failures,updated_at)
        VALUES (?,1,UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE failures=IF(updated_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 15 MINUTE),1,failures+1),updated_at=UTC_TIMESTAMP()");
    foreach ([auth_ip_key(),auth_email_key($email)] as $key) $statement->execute([$key]);
}
function auth_clear_failures(PDO $db, string $email): void {
    $statement=$db->prepare('DELETE FROM auth_attempts WHERE selector IN (?,?)');
    $statement->execute([auth_ip_key(),auth_email_key($email)]);
}
function auth_login(string $email, string $password): bool {
    session_start_safe();
    $db = pdo(); auth_migrate($db);
    $email = auth_normalize_email($email);
    if (auth_limited($db,$email)) return false;
    $stmt=$db->prepare('SELECT id,role,status,auth_version,password_hash FROM users WHERE email=? LIMIT 1');
    $stmt->execute([$email]);$row=$stmt->fetch();
    // Match timing characteristics of a password check even for unknown emails.
    $valid=password_verify($password,$row ? (string)$row['password_hash'] : '$2y$10$UwskgMDyw12d6JpPT8mxguUeOvS2uZNGtn/4G8EW8QovL6KTaY0mC') && (bool)$row;
    if (!$valid || $row['status']!=='active') {auth_note_failure($db,$email);return false;}
    if (password_needs_rehash((string)$row['password_hash'],PASSWORD_DEFAULT)) {
        $db->prepare('UPDATE users SET password_hash=? WHERE id=?')->execute([auth_hash_password($password),$row['id']]);
    }
    auth_clear_failures($db,$email);
    session_regenerate_id(true);
    unset($_SESSION['csrf']);
    $_SESSION['user_id']=(int)$row['id'];
    $_SESSION['auth_version']=(int)$row['auth_version'];
    $_SESSION['auth_started']=time();$_SESSION['auth_last']=time();
    unset($_SESSION['pending_auth_token']);
    csrf_token();
    return true;
}
function auth_logout(): void {
    session_start_safe();
    $_SESSION=[];
    if (ini_get('session.use_cookies')) {
        $p=session_get_cookie_params();
        setcookie(session_name(),'',time()-3600,$p['path'],$p['domain'],$p['secure'],$p['httponly']);
    }
    session_destroy();
}
function auth_current_user(): ?array {
    session_start_safe();
    if (empty($_SESSION['user_id']) || empty($_SESSION['auth_version'])) return null;
    $now=time();
    if ($now-(int)($_SESSION['auth_last']??0)>AUTH_IDLE_SECONDS ||
        $now-(int)($_SESSION['auth_started']??0)>AUTH_ABSOLUTE_SECONDS) {
        auth_logout();return null;
    }
    $db=pdo();auth_migrate($db);
    $stmt=$db->prepare('SELECT id,email,role,status,auth_version FROM users WHERE id=? LIMIT 1');
    $stmt->execute([(int)$_SESSION['user_id']]);$user=$stmt->fetch();
    if (!$user || $user['status']!=='active' || (int)$user['auth_version']!==(int)$_SESSION['auth_version']) {
        auth_logout();return null;
    }
    $_SESSION['auth_last']=$now;
    return $user;
}
function auth_require_user(string $minimum='viewer'): array {
    $user=auth_current_user();
    if (!$user) {
        http_response_code(401);
        throw new RuntimeException('Please sign in to access the photo library.');
    }
    if (!auth_role_allowed((string)$user['role'],$minimum)) {
        http_response_code(403);
        throw new RuntimeException('You do not have permission for this action.');
    }
    return $user;
}
function auth_token_format(string $token): bool { return (bool)preg_match('/\A[a-f0-9]{64}\z/D',$token); }
/** The raw token is returned once to the administrator and never stored in the database. */
function auth_issue_token(PDO $db, int $userId, string $purpose): string {
    if (!in_array($purpose,['invite','reset'],true)) throw new InvalidArgumentException('Unsupported token purpose');
    $raw=bin2hex(random_bytes(32));$hash=hash('sha256',$raw);
    $db->prepare('DELETE FROM auth_tokens WHERE user_id=? AND purpose=?')->execute([$userId,$purpose]);
    $ttl=$purpose==='invite'?24:1;
    $stmt=$db->prepare('INSERT INTO auth_tokens(user_id,token_hash,purpose,expires_at) VALUES (?,?,?,DATE_ADD(UTC_TIMESTAMP(),INTERVAL '.$ttl.' HOUR))');
    $stmt->execute([$userId,$hash,$purpose]);
    return $raw;
}
function auth_token_user(PDO $db, string $tokenHash): ?array {
    if (!auth_token_format($tokenHash)) return null;
    $stmt=$db->prepare("SELECT t.id AS token_id,t.purpose,u.id,u.email,u.role,u.status
        FROM auth_tokens t JOIN users u ON t.user_id=u.id
        WHERE t.token_hash=? AND t.used_at IS NULL AND t.expires_at>UTC_TIMESTAMP() LIMIT 1");
    $stmt->execute([$tokenHash]);$result=$stmt->fetch();
    if (!$result || ($result['purpose']==='invite' && $result['status']!=='pending') ||
        ($result['purpose']==='reset' && $result['status']!=='active')) return null;
    return $result;
}
function auth_complete_token(PDO $db, string $tokenHash, string $password): bool {
    if (!auth_token_format($tokenHash)) return false;
    $db->beginTransaction();
    try {
        $stmt=$db->prepare("SELECT t.id AS token_id,t.purpose,u.id AS user_id,u.status
            FROM auth_tokens t JOIN users u ON t.user_id=u.id
            WHERE t.token_hash=? AND t.used_at IS NULL AND t.expires_at>UTC_TIMESTAMP() FOR UPDATE");
        $stmt->execute([$tokenHash]);$result=$stmt->fetch();
        if (!$result || ($result['purpose']==='invite' && $result['status']!=='pending') ||
            ($result['purpose']==='reset' && $result['status']!=='active')) {$db->rollBack();return false;}
        $db->prepare("UPDATE users SET password_hash=?,status='active',auth_version=auth_version+1 WHERE id=?")
            ->execute([auth_hash_password($password),$result['user_id']]);
        $db->prepare('UPDATE auth_tokens SET used_at=UTC_TIMESTAMP() WHERE id=?')->execute([$result['token_id']]);
        $db->prepare('DELETE FROM auth_tokens WHERE user_id=?')->execute([$result['user_id']]);
        $db->commit();return true;
    } catch(Throwable $e) {$db->rollBack();throw $e;}
}
function auth_change_password(PDO $db,int $userId,string $current,string $new): bool {
    $stmt=$db->prepare("SELECT password_hash FROM users WHERE id=? AND status='active'");
    $stmt->execute([$userId]);$hash=$stmt->fetchColumn();
    if (!is_string($hash) || !password_verify($current,$hash)) return false;
    $db->prepare('UPDATE users SET password_hash=?,auth_version=auth_version+1 WHERE id=?')->execute([auth_hash_password($new),$userId]);
    $db->prepare('DELETE FROM auth_tokens WHERE user_id=?')->execute([$userId]);
    return true;
}
