<?php
declare(strict_types=1);
require_once __DIR__.'/auth.php';

const API_MAX_ACTIVE_TOKENS = 10;
const API_MAX_REQUESTS_PER_5_MINUTES = 120;
const API_TOKEN_PREFIX = 'glpm_v1_';

/** Independent, additive migration. Never touches photos or changes existing login sessions. */
function api_tokens_migrate(PDO $db): void {
    if (is_file(private_path('api-v1-ready'))) return;
    $lock = fopen(private_path('api-v1-migrate.lock'), 'c');
    if (!$lock || !flock($lock, LOCK_EX)) throw new RuntimeException('API migration lock unavailable');
    try {
        if (is_file(private_path('api-v1-ready'))) return;
        $db->exec("CREATE TABLE IF NOT EXISTS api_tokens (
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
        $db->exec("CREATE TABLE IF NOT EXISTS api_rate_limits (
            token_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
            hits INT UNSIGNED NOT NULL DEFAULT 0,
            window_started DATETIME NOT NULL,
            CONSTRAINT fk_api_rate_token FOREIGN KEY (token_id) REFERENCES api_tokens(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
        $tmp = private_path('api-v1-ready.tmp');
        if (file_put_contents($tmp, "ready\n", LOCK_EX)===false || !rename($tmp,private_path('api-v1-ready'))) {
            throw new RuntimeException('API migration could not save completion marker');
        }
        @chmod(private_path('api-v1-ready'),0600);
    } finally { flock($lock,LOCK_UN); fclose($lock); }
}
function api_token_format(string $token): bool {
    return (bool) preg_match('/\Aglpm_v1_[a-f0-9]{64}\z/D', $token);
}
function api_bearer_from_header(mixed $header): ?string {
    if (!is_string($header) || strlen($header) > 200) return null;
    if (!preg_match('/\ABearer (glpm_v1_[a-f0-9]{64})\z/D', trim($header),$m)) return null;
    return $m[1];
}
function api_authorization_header(): ?string {
    foreach (['HTTP_AUTHORIZATION','REDIRECT_HTTP_AUTHORIZATION'] as $key) {
        if (isset($_SERVER[$key]) && is_string($_SERVER[$key])) return $_SERVER[$key];
    }
    if (function_exists('getallheaders')) {
        foreach (getallheaders() as $key=>$value) {
            if (strcasecmp((string)$key,'Authorization')===0 && is_string($value)) return $value;
        }
    }
    return null;
}
function api_role_permitted(string $role,string $scope,string $needed): bool {
    if (!in_array($scope,['read','write'],true)) return false;
    if ($needed==='read') return auth_role_allowed($role,'viewer');
    if ($needed==='write') return $scope==='write' && auth_role_allowed($role,'editor');
    return false;
}
function api_issue_token(PDO $db,int $userId,string $label,string $scope,int $days): array {
    $label=trim($label);
    if ($label==='' || strlen($label)>80 || preg_match('/[\x00-\x1f\x7f]/',$label))
        throw new InvalidArgumentException('Token label must have 1-80 printable characters');
    if (!in_array($scope,['read','write'],true)) throw new InvalidArgumentException('Invalid token scope');
    if (!in_array($days,[1,7,30,90],true)) throw new InvalidArgumentException('Invalid expiry');
    $stmt=$db->prepare("SELECT role,status,auth_version FROM users WHERE id=? LIMIT 1");
    $stmt->execute([$userId]);$user=$stmt->fetch();
    if (!$user || $user['status']!=='active' || !api_role_permitted((string)$user['role'],$scope,$scope))
        throw new RuntimeException('Your account cannot issue this token');
    $stmt=$db->prepare('SELECT COUNT(*) FROM api_tokens WHERE user_id=? AND revoked_at IS NULL AND expires_at>UTC_TIMESTAMP() AND auth_version=?');
    $stmt->execute([$userId,$user['auth_version']]);
    if ((int)$stmt->fetchColumn()>=API_MAX_ACTIVE_TOKENS) throw new RuntimeException('Maximum active tokens reached; revoke an unused token first');
    $raw=API_TOKEN_PREFIX.bin2hex(random_bytes(32));
    $hash=hash('sha256',$raw);
    $stmt=$db->prepare('INSERT INTO api_tokens(user_id,token_hash,label,scope,auth_version,expires_at) VALUES(?,?,?,?,?,DATE_ADD(UTC_TIMESTAMP(),INTERVAL '.$days.' DAY))');
    $stmt->execute([$userId,$hash,$label,$scope,(int)$user['auth_version']]);
    return ['id'=>(int)$db->lastInsertId(),'token'=>$raw,'scope'=>$scope,'expires_in_days'=>$days];
}
function api_revoke_token(PDO $db,int $userId,int $tokenId): bool {
    $stmt=$db->prepare('UPDATE api_tokens SET revoked_at=UTC_TIMESTAMP() WHERE id=? AND user_id=? AND revoked_at IS NULL');
    $stmt->execute([$tokenId,$userId]);return $stmt->rowCount()===1;
}
function api_token_list(PDO $db,int $userId): array {
    $stmt=$db->prepare('SELECT id,label,scope,created_at,last_used_at,expires_at,revoked_at FROM api_tokens WHERE user_id=? ORDER BY id DESC LIMIT 40');
    $stmt->execute([$userId]);return $stmt->fetchAll();
}
function api_request_limit(PDO $db,int $tokenId): bool {
    $stmt=$db->prepare("INSERT INTO api_rate_limits(token_id,hits,window_started) VALUES (?,1,UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE
        hits=IF(window_started<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 5 MINUTE),1,hits+1),
        window_started=IF(window_started<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 5 MINUTE),UTC_TIMESTAMP(),window_started)");
    $stmt->execute([$tokenId]);
    $stmt=$db->prepare('SELECT hits FROM api_rate_limits WHERE token_id=?');$stmt->execute([$tokenId]);
    return (int)$stmt->fetchColumn() <= API_MAX_REQUESTS_PER_5_MINUTES;
}
/** No session-cookie fallback: clients must explicitly supply a token in the Authorization header. */
function api_authenticated_user(PDO $db): ?array {
    $raw=api_bearer_from_header(api_authorization_header());
    if ($raw===null) return null;
    $stmt=$db->prepare("SELECT t.id AS token_id,t.scope,t.user_id,u.email,u.role,u.auth_version
        FROM api_tokens t JOIN users u ON u.id=t.user_id
        WHERE t.token_hash=? AND t.revoked_at IS NULL AND t.expires_at>UTC_TIMESTAMP()
          AND u.status='active' AND t.auth_version=u.auth_version LIMIT 1");
    $stmt->execute([hash('sha256',$raw)]);$user=$stmt->fetch();
    if (!$user) return null;
    if (!api_request_limit($db,(int)$user['token_id'])) {
        http_response_code(429);header('Retry-After: 300');
        return ['rate_limited'=>true];
    }
    $stmt=$db->prepare('UPDATE api_tokens SET last_used_at=UTC_TIMESTAMP() WHERE id=? AND (last_used_at IS NULL OR last_used_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 5 MINUTE))');
    $stmt->execute([(int)$user['token_id']]);
    return $user;
}
