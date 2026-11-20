<?php
declare(strict_types=1);

const APP_PRIVATE = __DIR__;
const MAX_FILE_BYTES = 26214400; // 25 MiB; PHP's actual upload cap may be lower.
const MAX_PIXELS = 28000000;
const BATCH_SIZE = 12;

// HTTPS is mandatory for a deployed app handling private photos.
if (PHP_SAPI !== 'cli' && (!isset($_SERVER['HTTPS']) || $_SERVER['HTTPS']==='off') &&
    !in_array($_SERVER['SERVER_NAME'] ?? '', ['localhost','127.0.0.1'], true)) {
    http_response_code(403);
    exit('HTTPS is required. Enable a certificate for this domain.');
}

if (PHP_SAPI !== 'cli') {
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    header('X-Robots-Tag: noindex, nofollow');
    header('X-Frame-Options: DENY');
    header('Content-Security-Policy: default-src \'self\'; img-src \'self\' data: blob:; style-src \'self\'; script-src \'self\'; connect-src \'self\'; object-src \'none\'; base-uri \'self\'; form-action \'self\'');
}

function private_path(string $child): string { return APP_PRIVATE . DIRECTORY_SEPARATOR . $child; }
function installed(): bool { return is_file(private_path('config.php')); }
function config(): array {
    static $config;
    if ($config === null) {
        if (!installed()) { throw new RuntimeException('Application not installed'); }
        $config = require private_path('config.php');
    }
    return $config;
}
function pdo(): PDO {
    static $pdo;
    if ($pdo === null) {
        $c = config();
        $pdo = new PDO('mysql:host=' . $c['db_host'] . ';dbname=' . $c['db_name'] . ';charset=utf8mb4',
            $c['db_user'], $c['db_pass'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC, PDO::ATTR_EMULATE_PREPARES => false]);
    }
    return $pdo;
}
function session_start_safe(): void {
    if (session_status() === PHP_SESSION_ACTIVE) return;
    session_name('GLPMSESSID');
    session_set_cookie_params(['lifetime'=>0,'path'=>'/','secure'=>PHP_SAPI === 'cli' ? false : !in_array($_SERVER['SERVER_NAME'] ?? '', ['localhost','127.0.0.1'], true),
        'httponly'=>true,'samesite'=>'Lax']);
    session_start();
}
function csrf_token(): string {
    session_start_safe();
    return $_SESSION['csrf'] ??= bin2hex(random_bytes(24));
}
function verify_csrf(): void {
    session_start_safe();
    $sent = $_POST['csrf'] ?? $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    if (!is_string($sent) || !hash_equals(csrf_token(), $sent)) {
        http_response_code(403); throw new RuntimeException('Invalid security token; reload and try again');
    }
}
function require_login(): int {
    session_start_safe();
    if (!isset($_SESSION['user_id'])) {
        http_response_code(401);
        if (str_contains($_SERVER['SCRIPT_NAME'] ?? '', 'index.php')) { header('Location: index.php'); }
        throw new RuntimeException('Please sign in to access the photo library.');
    }
    return (int) $_SESSION['user_id'];
}
function clean_text(mixed $value, int $limit = 190): string {
    if (!is_string($value)) return '';
    return function_exists('mb_substr') ? mb_substr(trim(preg_replace('/[\x00-\x1F\x7F]/u', ' ', $value) ?? ''), 0, $limit) : substr(trim($value), 0, $limit);
}
function supported_mime(string $file): ?string {
    if (!is_file($file)) return null;
    $mime = (new finfo(FILEINFO_MIME_TYPE))->file($file);
    return in_array($mime, ['image/jpeg','image/png','image/webp'], true) ? $mime : null;
}
function ensure_dirs(): void {
    foreach (['originals','thumbnails','incoming','rejected','tmp'] as $dir) {
        $path = private_path($dir);
        if (!is_dir($path) && !mkdir($path,0700,true) && !is_dir($path)) throw new RuntimeException('Cannot create data directory');
    }
}
function photo_path(array $row, bool $thumb=false): string {
    $name = $row['stored_name'];
    if (!is_string($name) || !preg_match('/\A[a-f0-9]{40}\.(jpe?g|png|webp)\z/', $name)) throw new RuntimeException('Invalid filename in database');
    return private_path(($thumb ? 'thumbnails/' : 'originals/') . $name . ($thumb ? '.jpg' : ''));
}
function respond(array $data, int $status=200): never {
    http_response_code($status);header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);exit;
}
function method_post(): void { if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {http_response_code(405);throw new RuntimeException('POST required');} }
function int_id(mixed $value): int { $n = filter_var($value,FILTER_VALIDATE_INT,['options'=>['min_range'=>1]]); if ($n === false) throw new RuntimeException('Invalid photo id'); return $n; }
