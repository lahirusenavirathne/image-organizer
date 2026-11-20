<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/bootstrap.php';
if(installed()){header('Location: index.php');exit;}
if(!is_dir(APP_PRIVATE) || !is_writable(APP_PRIVATE)) {http_response_code(500);exit('The private folder must be writable by the PHP user.');}
$token_file=private_path('install-token.txt');
if(!is_file($token_file)){
    $handle=@fopen($token_file,'x');
    if(!$handle) {http_response_code(500);exit('Cannot create one-time setup token');}
    fwrite($handle,bin2hex(random_bytes(20)));fclose($handle);@chmod($token_file,0600);
}
$error='';
if($_SERVER['REQUEST_METHOD']==='POST'){
 try{
    $expected=trim((string)file_get_contents($token_file));
    $submitted=(string)($_POST['install_token']??'');
    if(!hash_equals($expected,$submitted))throw new RuntimeException('Incorrect one-time setup token. Read private/install-token.txt via SFTP.');
    $email=filter_var($_POST['email']??'',FILTER_VALIDATE_EMAIL);
    $password=(string)($_POST['password']??'');
    if(!$email || strlen($password)<14)throw new RuntimeException('Use a valid email and an admin password of 14 characters or more');
    foreach(['db_host','db_name','db_user','db_pass'] as $key) if(!isset($_POST[$key]) || !is_string($_POST[$key]) || trim($_POST[$key])==='') throw new RuntimeException('All MySQL settings are required');
    $host=trim($_POST['db_host']);$name=trim($_POST['db_name']);$user=trim($_POST['db_user']);$pass=$_POST['db_pass'];
    if(!preg_match('/\A[a-zA-Z0-9._-]+\z/',$host)||!preg_match('/\A[a-zA-Z0-9_\-]+\z/',$name))throw new RuntimeException('Invalid MySQL host or database name');
    if(!extension_loaded('pdo_mysql') || !gd_supported_installer())throw new RuntimeException('Enable PHP extensions pdo_mysql and GD before setup');
    $dbh=new PDO("mysql:host=$host;dbname=$name;charset=utf8mb4",$user,$pass,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
    $schema=(string)file_get_contents(private_path('schema.sql'));
    foreach(explode(';',$schema) as $sql){ if(trim($sql)!=='')$dbh->exec($sql); }
    $stm=$dbh->prepare('SELECT COUNT(*) FROM users');$stm->execute();
    if((int)$stm->fetchColumn()>0)throw new RuntimeException('This database already has an administrator. Use a new database for a new installation.');
    $stm=$dbh->prepare('INSERT INTO users(email,password_hash) VALUES (?,?)');$stm->execute([$email,password_hash($password,PASSWORD_DEFAULT)]);
    $settings=['db_host'=>$host,'db_name'=>$name,'db_user'=>$user,'db_pass'=>$pass,'openai_api_key'=>''];
    $temp=private_path('config.php.tmp');
    if(file_put_contents($temp,"<?php\nreturn ".var_export($settings,true).";\n",LOCK_EX)===false)throw new RuntimeException('Cannot save private configuration');
    @chmod($temp,0600);
    if(!rename($temp,private_path('config.php')))throw new RuntimeException('Cannot finalize private configuration');
    @unlink($token_file);ensure_dirs();
    header('Location: index.php?installed=1');exit;
 }catch(Throwable $e){ error_log('GLPM setup: '.get_class($e).': '.$e->getMessage());$error= $e instanceof PDOException?'Database connection failed. Check MySQL hostname and credentials.':$e->getMessage(); }
}
function gd_supported_installer():bool{return extension_loaded('gd')&&function_exists('imagecreatetruecolor');}
function e(string $s):string{return htmlspecialchars($s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Install · Guia Lanka Photo Manager</title><link rel="stylesheet" href="assets/style.css"></head><body class="auth-bg"><main class="auth-card"><div class="eyebrow">ONE-TIME SETUP</div><h1>Guia Lanka Photo Manager</h1><p>Create a MySQL database in DreamHost first, then retrieve the installation token from <code>private/install-token.txt</code> using SFTP.</p><?php if($error):?><p role="alert" class="alert"><?=e($error)?></p><?php endif;?><form method="post" class="stack"><label>Setup token<input name="install_token" required autocomplete="off"></label><label>Database hostname<input name="db_host" placeholder="mysql.example.com" required></label><label>Database name<input name="db_name" required></label><label>Database user<input name="db_user" required></label><label>Database password<input name="db_pass" type="password" required></label><label>Administrator email<input name="email" type="email" required autocomplete="username"></label><label>Administrator password (14+ characters)<input name="password" type="password" minlength="14" required autocomplete="new-password"></label><button class="button primary" type="submit">Install private photo library</button></form><p class="fine">The token is not exposed over the web. Setup automatically disables itself after installation.</p></main></body></html>
