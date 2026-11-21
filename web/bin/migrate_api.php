<?php
declare(strict_types=1);
if (PHP_SAPI!=='cli') { http_response_code(403); exit("CLI only\n"); }
require_once dirname(__DIR__).'/private/api_tokens.php';
require_once dirname(__DIR__).'/private/drive.php';
if (!installed()) exit("Install the photo manager before API migration\n");
$db=pdo();auth_migrate($db);drive_migrate($db);api_tokens_migrate($db);
echo "REST API v1 token tables ready. Existing photos and accounts unchanged.\n";
