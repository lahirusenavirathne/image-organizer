<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
if(!installed()){header('Location: install.php');exit;}
header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');
session_start_safe();$db=pdo();auth_migrate($db);
if(isset($_GET['token']) && is_string($_GET['token'])) {
    $raw=(string)$_GET['token'];
    unset($_SESSION['pending_auth_token']);
    if(auth_token_format($raw)){
        $hash=hash('sha256',$raw);
        if(auth_token_user($db,$hash))$_SESSION['pending_auth_token']=$hash;
    }
    header('Location: activate.php',true,303);exit;
}
$hash=(string)($_SESSION['pending_auth_token']??'');
$record=auth_token_user($db,$hash);
$error='';
if(($_SERVER['REQUEST_METHOD']??'')==='POST' && $record){
    try {
        verify_csrf();
        $password=(string)($_POST['password']??'');
        auth_validate_password($password,(string)($_POST['confirm_password']??''));
        if(!auth_complete_token($db,$hash,$password))throw new RuntimeException('This link has expired or has already been used.');
        unset($_SESSION['pending_auth_token']);
        header('Location: index.php?password_set=1',true,303);exit;
    }catch(Throwable $ex){$error=$ex->getMessage();}
}
function e(string $s):string{return htmlspecialchars($s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Set your password · Guia Lanka Photo Manager</title><link rel="stylesheet" href="assets/style.css"></head>
<body class="auth-bg"><main class="auth-card"><div class="brand-badge">GL</div><div class="eyebrow">SECURE ACCOUNT ACCESS</div><h1><?=($record && $record['purpose']==='invite')?'Activate your account':'Set a new password'?></h1>
<?php if(!$record):?><p role="alert" class="alert">This activation or reset link has expired or is invalid. Ask an administrator for a new link.</p><p><a href="index.php">Return to sign in</a></p>
<?php else:?><p>Account: <strong><?=e($record['email'])?></strong>. Choose a unique password with at least 14 characters.</p>
<?php if($error):?><p role="alert" class="alert"><?=e($error)?></p><?php endif;?>
<form method="post" class="stack"><input type="hidden" name="csrf" value="<?=e(csrf_token())?>">
<label>New password<input name="password" type="password" minlength="14" maxlength="72" autocomplete="new-password" required></label>
<label>Confirm password<input name="confirm_password" type="password" minlength="14" maxlength="72" autocomplete="new-password" required></label>
<button class="button primary" type="submit">Save password</button></form>
<?php endif;?></main></body></html>
