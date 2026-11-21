<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/api_tokens.php';
try {$user=auth_require_user();}catch(Throwable){header('Location: index.php',true,303);exit;}
header('Cache-Control: no-store');
$db=pdo();api_tokens_migrate($db);
$error='';$success='';
if (($_SERVER['REQUEST_METHOD']??'')==='POST') {
    try {
        verify_csrf();
        $action=(string)($_POST['action']??'');
        if ($action==='issue') {
            if (auth_limited($db,(string)$user['email'])) throw new RuntimeException('Too many attempts; retry later');
            $stmt=$db->prepare('SELECT password_hash FROM users WHERE id=? AND status=\'active\'');
            $stmt->execute([(int)$user['id']]);$hash=$stmt->fetchColumn();
            if (!is_string($hash)||!password_verify((string)($_POST['password']??''),$hash)) {
                auth_note_failure($db,(string)$user['email']);throw new RuntimeException('Current password is incorrect');
            }
            auth_clear_failures($db,(string)$user['email']);
            $issued=api_issue_token($db,(int)$user['id'],(string)($_POST['label']??''),(string)($_POST['scope']??'read'),(int)($_POST['days']??30));
            $_SESSION['api_new_token']=$issued['token'];
            header('Location: api-tokens.php?created=1',true,303);exit;
        }
        if ($action==='revoke') {
            $id=int_id($_POST['token_id']??null);
            $success=api_revoke_token($db,(int)$user['id'],$id)?'Token revoked. Requests using it will be denied.':'Token was already revoked.';
        } else if($action!=='issue') throw new RuntimeException('Unknown action');
    }catch(Throwable $e){$error=$e instanceof PDOException?'Unable to update tokens right now':$e->getMessage();}
}
$newToken='';
if (($_GET['created']??'')==='1' && isset($_SESSION['api_new_token'])) {
    $newToken=(string)$_SESSION['api_new_token'];unset($_SESSION['api_new_token']);
}
$tokens=api_token_list($db,(int)$user['id']);
function esc_api(string $value): string {return htmlspecialchars($value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>API access - Guia Lanka Photo Manager</title><link rel="stylesheet" href="assets/style.css"></head>
<body class="auth-bg"><main class="auth-card auth-wide"><div class="brand-badge">GL</div><div class="eyebrow">DEVELOPER ACCESS</div><h1>API tokens</h1><p>Use personal, revocable API tokens to connect approved apps to your photo library. Tokens are separate from browser passwords.</p>
<?php if($error!==''):?><p class="alert" role="alert"><?=esc_api($error)?></p><?php endif;?>
<?php if($success!==''):?><p class="notice" role="status"><?=esc_api($success)?></p><?php endif;?>
<?php if($newToken!==''):?><section class="account-section"><h2>Copy this token now</h2><p><strong>The full token will never be shown again.</strong> Store it in Windows Credential Manager or another secret store, not in GitHub or a URL.</p><label for="new-api-token">Your new API token</label><input id="new-api-token" type="text" readonly spellcheck="false" value="<?=esc_api($newToken)?>" class="api-token-value"><button type="button" class="small-button" id="copy-api-token">Copy token</button><p class="fine">All API calls require HTTPS and the Authorization: Bearer header.</p></section><?php endif;?>
<section class="account-section"><h2>Create a token</h2><form method="post" class="stack"><input type="hidden" name="csrf" value="<?=esc_api(csrf_token())?>"><input type="hidden" name="action" value="issue">
<label>Device or integration name<input name="label" type="text" maxlength="80" placeholder="Windows desktop" required></label>
<label>Access level<select name="scope"><option value="read">Read-only (browse and preview)</option><?php if(auth_role_allowed((string)$user['role'],'editor')):?><option value="write">Read + write (upload, edit, Trash)</option><?php endif;?></select></label>
<label>Expires in<select name="days"><option value="1">1 day</option><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option></select></label>
<label>Confirm your current password<input name="password" type="password" autocomplete="current-password" required></label>
<button class="button primary" type="submit">Create token</button></form><p class="fine">At most ten active tokens per account. Changing your password or disabling your user account invalidates issued tokens.</p></section>
<section class="account-section"><h2>Your tokens</h2>
<?php if(!$tokens):?><p class="fine">No tokens created.</p><?php endif;?>
<?php foreach($tokens as $token):?><article class="account-item"><div><strong><?=esc_api((string)$token['label'])?></strong> <span class="role-pill"><?=esc_api((string)$token['scope'])?></span><p class="fine">Created <?=esc_api((string)$token['created_at'])?> | Expires <?=esc_api((string)$token['expires_at'])?> | Last used <?=esc_api((string)($token['last_used_at']??'Never'))?></p></div>
<?php if($token['revoked_at']===null):?><form method="post"><input type="hidden" name="csrf" value="<?=esc_api(csrf_token())?>"><input type="hidden" name="action" value="revoke"><input type="hidden" name="token_id" value="<?=esc_api((string)$token['id'])?>"><button class="small-button" type="submit">Revoke</button></form><?php else:?><span class="fine">Revoked</span><?php endif;?></article><?php endforeach;?></section>
<p><a href="account.php">Account &amp; password</a> | <a href="index.php">Photo library</a></p>
</main><script src="assets/api-tokens.js" defer></script></body></html>
