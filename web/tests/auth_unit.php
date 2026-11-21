<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/auth.php';
function expect(bool $ok,string $description): void {
    if(!$ok){fwrite(STDERR,"FAIL: $description\n");exit(1);}echo "PASS: $description\n";
}
expect(auth_role_allowed('admin','admin'),'Admin can manage users');
expect(auth_role_allowed('admin','viewer'),'Admin can browse');
expect(auth_role_allowed('editor','viewer'),'Editor can browse');
expect(!auth_role_allowed('editor','admin'),'Editor cannot manage users');
expect(!auth_role_allowed('viewer','editor'),'Viewer cannot edit');
expect(!auth_role_allowed('nonsense','viewer'),'Unknown role cannot access');
expect(auth_normalize_email('  User@Example.com  ')==='user@example.com','Email normalization');
expect(auth_normalize_email('not-an-email')==='','Invalid email rejected');
$pass='very-long-and-unique-test-passphrase';
expect(password_verify($pass,auth_hash_password($pass)),'Passwords are salted and verified');
auth_validate_password($pass,$pass);
try{auth_validate_password('short','short');expect(false,'Minimum password enforced');}catch(RuntimeException){expect(true,'Minimum password enforced');}
try{auth_validate_password($pass,$pass.'extra');expect(false,'Password confirmation enforced');}catch(RuntimeException){expect(true,'Password confirmation enforced');}
expect(auth_token_format(bin2hex(random_bytes(32))),'256-bit reset token format');
expect(!auth_token_format('abc/../token'),'Malformed reset token rejected');
expect(!auth_token_format(str_repeat('f',128)),'Overlong reset token rejected');
echo "Auth unit tests passed.\n";
