<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
if(PHP_SAPI!=='cli'){http_response_code(403);exit('CLI only');}
if(!installed()){fwrite(STDERR,"Install the app first.\n");exit(1);}
auth_migrate(pdo());
echo "Authentication tables and user permissions are ready. Existing administrator account preserved.\n";
