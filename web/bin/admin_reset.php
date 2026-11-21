<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
if(PHP_SAPI!=='cli'){http_response_code(403);exit('CLI only');}
if(!installed()){fwrite(STDERR,"Install the app first.\n");exit(1);}
$email=auth_normalize_email($argv[1]??null);
if(!$email){fwrite(STDERR,"Usage: php bin/admin_reset.php admin@example.com\n");exit(1);}
$db=pdo();auth_migrate($db);
$stmt=$db->prepare("SELECT id FROM users WHERE email=? AND role='admin' AND status='active' LIMIT 1");
$stmt->execute([$email]);$id=$stmt->fetchColumn();
if(!$id){fwrite(STDERR,"No active administrator matches that email.\n");exit(1);}
$token=auth_issue_token($db,(int)$id,'reset');
echo "One-time password reset path (expires in 1 hour):\n";
echo 'activate.php?token='.$token."\n";
echo "Append this path to your HTTPS application domain. Keep it private and use it once.\n";
