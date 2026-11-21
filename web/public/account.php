<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
try { $me=auth_require_user(); }
catch(Throwable) { header('Location: index.php');exit; }
header('Cache-Control: no-store');
$error='';$success='';
if(($_SERVER['REQUEST_METHOD']??'')==='POST'){
    try {
        verify_csrf();
        $new=(string)($_POST['new_password']??'');
        auth_validate_password($new,(string)($_POST['confirm_password']??''));
        if (!auth_change_password(pdo(),(int)$me['id'],(string)($_POST['current_password']??''),$new)) {
            throw new RuntimeException('Current password is incorrect.');
        }
        session_regenerate_id(true);
        $stmt=pdo()->prepare('SELECT auth_version FROM users WHERE id=?');$stmt->execute([$me['id']]);
        $_SESSION['auth_version']=(int)$stmt->fetchColumn();
        $_SESSION['auth_started']=time();$_SESSION['auth_last']=time();
        $success='Password updated. Other sessions have been signed out.';
    } catch(Throwable $ex) {$error=$ex->getMessage();}
}
function e(string $s):string{return htmlspecialchars($s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Account security · Guia Lanka Photo Manager</title><link rel="stylesheet" href="assets/style.css"></head>
<body class="auth-bg"><main class="auth-card"><div class="brand-badge">GL</div><div class="eyebrow">ACCOUNT SECURITY</div><h1>Your account</h1><p>Signed in as <strong><?=e($me['email'])?></strong> (<?=e($me['role'])?>).</p>
<?php if($error):?><p role="alert" class="alert"><?=e($error)?></p><?php endif;?>
<?php if($success):?><p role="status" class="notice"><?=e($success)?></p><?php endif;?>
<form method="post" class="stack"><input type="hidden" name="csrf" value="<?=e(csrf_token())?>">
<label>Current password<input name="current_password" type="password" autocomplete="current-password" required></label>
<p class="fine" id="password-help">Choose a unique password with at least 14 characters.</p>
<label>New password<input name="new_password" type="password" minlength="14" maxlength="72" autocomplete="new-password" aria-describedby="password-help" required></label>
<label>Confirm new password<input name="confirm_password" type="password" minlength="14" maxlength="72" autocomplete="new-password" required></label>
<button class="button primary" type="submit">Update password</button></form>
<p><a href="api-tokens.php">Manage API tokens</a></p>
<p><a href="index.php">← Back to photo library</a></p></main></body></html>
