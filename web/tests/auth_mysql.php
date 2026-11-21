<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
// Run ONLY against a disposable test database, never your production photo library.
$dsn=getenv('GLPM_TEST_MYSQL_DSN')?:'';
if(!$dsn){echo "SKIP: set GLPM_TEST_MYSQL_DSN for MySQL integration tests.\n";exit(0);}
$db=new PDO($dsn,getenv('GLPM_TEST_MYSQL_USER')?:'root',getenv('GLPM_TEST_MYSQL_PASS')?:'',[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
$existing=$db->query("SHOW TABLES LIKE 'users'")->fetchColumn();
if($existing){fwrite(STDERR,"Refusing to test: database must have no existing users table.\n");exit(1);}
function check(bool $condition,string $description): void{if(!$condition){fwrite(STDERR,"FAIL: $description\n");exit(1);}echo "PASS: $description\n";}
// Simulate a v0.1 schema to verify automatic migration preserves the old account.
$db->exec("CREATE TABLE users(id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,email VARCHAR(190) NOT NULL UNIQUE,password_hash VARCHAR(255) NOT NULL,created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB");
$db->prepare('INSERT INTO users(email,password_hash) VALUES (?,?)')->execute(['admin@example.com',auth_hash_password('old-long-password-for-tests')]);
auth_migrate($db,true);
$admin=$db->query('SELECT * FROM users LIMIT 1')->fetch();
check($admin['role']==='admin'&&$admin['status']==='active','Legacy admin migrated');
check(password_verify('old-long-password-for-tests',$admin['password_hash']),'Password preserved');
$tokens=$db->query("SHOW TABLES LIKE 'auth_tokens'")->fetchAll();check(count($tokens)===1,'Token table created');
$inviteEmail='teammate@example.com';
$db->prepare("INSERT INTO users(email,password_hash,role,status) VALUES (?,?,?,'pending')")->execute([$inviteEmail,auth_hash_password(bin2hex(random_bytes(32))),'editor']);
$id=(int)$db->lastInsertId();
$invite=auth_issue_token($db,$id,'invite');$hash=hash('sha256',$invite);
check((bool)auth_token_user($db,$hash),'Invitation link valid');
check(!auth_token_user($db,$invite),'Raw token is not stored in table');
check(auth_complete_token($db,$hash,'some-good-unique-new-password'),'Invitation activated');
check(!auth_complete_token($db,$hash,'other-good-unique-password'),'Invitation cannot be reused');
$row=$db->query('SELECT * FROM users WHERE id='.$id)->fetch();
check($row['status']==='active'&&$row['role']==='editor','Role retained after activation');
$reset=auth_issue_token($db,$id,'reset');$resetHash=hash('sha256',$reset);
check(auth_complete_token($db,$resetHash,'another-long-unique-password'),'Password reset valid');
check(!auth_token_user($db,$resetHash),'Reset token revoked');
check(!password_verify('some-good-unique-new-password',$db->query('SELECT password_hash FROM users WHERE id='.$id)->fetchColumn()),'Old password invalidated');
for($i=0;$i<10;$i++)auth_note_failure($db,'admin@example.com');
check(auth_limited($db,'admin@example.com'),'Failed sign-ins are throttled across sessions');
auth_clear_failures($db,'admin@example.com');
check(!auth_limited($db,'admin@example.com'),'Successful sign-in can clear a lock');
$db->exec('DROP TABLE auth_tokens');$db->exec('DROP TABLE auth_attempts');$db->exec('DROP TABLE users');
echo "MySQL authentication migration and token tests passed.\n";
