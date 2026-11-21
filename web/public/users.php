<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
try {$me=auth_require_user('admin');}catch(Throwable){http_response_code(403);exit('Administrators only.');}
header('Cache-Control: no-store');
$db=pdo();$error='';$success='';$oneTimeLink='';
if(($_SERVER['REQUEST_METHOD']??'')==='POST') {
    try {
        verify_csrf();
        $action=(string)($_POST['action']??'');
        if($action==='invite') {
            $email=auth_normalize_email($_POST['email']??null);
            $role=(string)($_POST['role']??'viewer');
            if(!$email||!in_array($role,['admin','editor','viewer'],true))throw new RuntimeException('Provide a valid email address and role.');
            $stmt=$db->prepare('SELECT id,status FROM users WHERE email=?');$stmt->execute([$email]);$existing=$stmt->fetch();
            if($existing && $existing['status']!=='pending')throw new RuntimeException('An account already exists for this address. Use a reset link if necessary.');
            if($existing){
                $userId=(int)$existing['id'];
                $db->prepare('UPDATE users SET role=? WHERE id=?')->execute([$role,$userId]);
            }else{
                $disabledPassword=auth_hash_password(bin2hex(random_bytes(36)));
                $db->prepare("INSERT INTO users(email,password_hash,role,status) VALUES (?,?,?,'pending')")
                    ->execute([$email,$disabledPassword,$role]);
                $userId=(int)$db->lastInsertId();
            }
            $token=auth_issue_token($db,$userId,'invite');
            $oneTimeLink='activate.php?token='.$token;
            $success='Invitation created. Copy the one-time link below and share it privately. It expires in 24 hours.';
        } else {
            $id=int_id($_POST['user_id']??null);
            $db->beginTransaction();
            try {
                $st=$db->prepare('SELECT id,email,role,status FROM users WHERE id=? FOR UPDATE');$st->execute([$id]);$target=$st->fetch();
                if(!$target)throw new RuntimeException('Account not found.');
                if($action==='reset'){
                    if($target['status']!=='active')throw new RuntimeException('Only active accounts can receive password resets.');
                    $db->commit();
                    $token=auth_issue_token($db,$id,'reset');
                    $oneTimeLink='activate.php?token='.$token;
                    $success='Password-reset link created. It expires in one hour. Share privately with the account owner.';
                } elseif($action==='role'||$action==='disable'||$action==='enable') {
                    if($id===(int)$me['id'])throw new RuntimeException('You cannot change your own role or disable your own account here.');
                    if($action==='role'){
                        $role=(string)($_POST['role']??'');
                        if(!in_array($role,['admin','editor','viewer'],true))throw new RuntimeException('Invalid role.');
                        $changesAdmin=$target['role']==='admin'&&$target['status']==='active'&&$role!=='admin';
                        $newRole=$role;$newStatus=$target['status'];
                    }elseif($action==='disable'){
                        $changesAdmin=$target['role']==='admin'&&$target['status']==='active';
                        $newRole=$target['role'];$newStatus='disabled';
                    }else{
                        if($target['status']!=='disabled')throw new RuntimeException('Only disabled users can be re-enabled.');
                        $changesAdmin=false;$newRole=$target['role'];$newStatus='active';
                    }
                    if($changesAdmin){
                        $admins=$db->query("SELECT id FROM users WHERE role='admin' AND status='active' FOR UPDATE")->fetchAll();
                        if(count($admins)<2)throw new RuntimeException('At least one active administrator must remain.');
                    }
                    $db->prepare('UPDATE users SET role=?,status=?,auth_version=auth_version+1 WHERE id=?')
                        ->execute([$newRole,$newStatus,$id]);
                    $db->commit();
                    $success='Account permissions updated. Previous sessions for that user are no longer valid.';
                } else throw new RuntimeException('Unknown action.');
            }catch(Throwable $e){if($db->inTransaction())$db->rollBack();throw $e;}
        }
    }catch(Throwable $e){error_log('GLPM account management: '.get_class($e));$error=$e instanceof PDOException?'Could not update account. Check database permissions.':$e->getMessage();}
}
$users=$db->query('SELECT id,email,role,status,created_at FROM users ORDER BY id')->fetchAll();
function e(string $s):string{return htmlspecialchars($s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Team accounts · Guia Lanka Photo Manager</title><link rel="stylesheet" href="assets/style.css"></head><body class="auth-bg">
<main class="auth-card auth-wide"><div class="brand-badge">GL</div><div class="eyebrow">ACCESS CONTROL</div><h1>Team accounts</h1>
<p>Only administrators can invite people, change roles, or disable access. Registration is invitation-only.</p>
<?php if($error):?><p role="alert" class="alert"><?=e($error)?></p><?php endif;?>
<?php if($success):?><p role="status" class="notice"><?=e($success)?></p><?php endif;?>
<?php if($oneTimeLink):?>
<div class="invite-link-box"><label for="invite-link">One-time link (shown only now)</label><input readonly id="invite-link" value="<?=e($oneTimeLink)?>" aria-describedby="link-help"><p id="link-help" class="fine">Copy this address and share privately. Do not include invitation links in public messages or repository files.</p><button class="small-button" id="copy-invite" type="button">Copy full link</button></div>
<script>document.getElementById('copy-invite').addEventListener('click', async () => {const input=document.getElementById('invite-link');await navigator.clipboard.writeText(new URL(input.value,location.href).href);document.getElementById('copy-invite').textContent='Copied';});</script>
<?php endif;?>
<section class="account-section"><h2>Invite a teammate</h2><form method="post" class="account-form"><input type="hidden" name="csrf" value="<?=e(csrf_token())?>"><input type="hidden" name="action" value="invite">
<label>Email address<input type="email" name="email" maxlength="190" autocomplete="off" required></label>
<label>Role<select name="role"><option value="viewer">Viewer — browse photos</option><option value="editor">Editor — tag, upload and export</option><option value="admin">Admin — manage accounts and imports</option></select></label>
<button class="button primary" type="submit">Create invitation</button></form></section>
<section class="account-section"><h2>Existing accounts</h2><div class="account-list">
<?php foreach($users as $user):?><article class="account-item"><div><strong><?=e($user['email'])?></strong> <span class="role-pill"><?=e($user['role'])?> · <?=e($user['status'])?></span><p class="fine">Created <?=e((string)$user['created_at'])?></p></div>
<?php if((int)$user['id']!==(int)$me['id']):?>
<div class="account-actions"><form method="post"><input type="hidden" name="csrf" value="<?=e(csrf_token())?>"><input type="hidden" name="user_id" value="<?=e((string)$user['id'])?>"><input type="hidden" name="action" value="role"><label class="sr-only" for="role-<?=e((string)$user['id'])?>">Role</label><select name="role" id="role-<?=e((string)$user['id'])?>"><?php foreach(['viewer','editor','admin'] as $role):?><option value="<?=$role?>" <?=$user['role']===$role?'selected':''?>><?=ucfirst($role)?></option><?php endforeach;?></select><button class="small-button">Update role</button></form>
<form method="post"><input type="hidden" name="csrf" value="<?=e(csrf_token())?>"><input type="hidden" name="user_id" value="<?=e((string)$user['id'])?>"><input type="hidden" name="action" value="<?=$user['status']==='disabled'?'enable':'disable'?>"><button class="small-button" type="submit"><?=$user['status']==='disabled'?'Enable':'Disable'?></button></form>
<?php if($user['status']==='active'):?><form method="post"><input type="hidden" name="csrf" value="<?=e(csrf_token())?>"><input type="hidden" name="user_id" value="<?=e((string)$user['id'])?>"><input type="hidden" name="action" value="reset"><button class="small-button" type="submit">Reset password</button></form><?php endif;?></div>
<?php endif;?></article><?php endforeach;?></div></section>
<p><a href="index.php">← Back to photo library</a> · <a href="account.php">My account</a></p>
</main></body></html>
