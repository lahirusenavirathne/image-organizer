<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
if(($_SERVER['REQUEST_METHOD']??'')!=='POST'){http_response_code(405);exit('POST required');}
verify_csrf();
auth_logout();
header('Cache-Control: no-store');
header('Location: index.php');
exit;
