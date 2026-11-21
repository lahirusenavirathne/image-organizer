<?php
/** Safe sync tests that run without a MySQL server. */
declare(strict_types=1);
require_once dirname(__DIR__).'/private/api_v1_helpers.php';
function check(bool $condition,string $reason): void {if (!$condition)throw new RuntimeException($reason);}
$sha=str_repeat('a',64);
check(api_sync_sha($sha)===$sha,'valid SHA');
foreach([str_repeat('g',64),'',str_repeat('a',63),strtoupper($sha)] as $bad) {
    try {api_sync_sha($bad);throw new RuntimeException('accepted invalid SHA');}catch(ApiBadRequest $e){}
}
check(api_sync_decision([], $sha,'one.jpg')['decision']==='upload','new file');
check(api_sync_decision([['id'=>7,'sha256'=>$sha,'original_name'=>'other.jpg']],$sha,'one.jpg')['decision']==='duplicate','hash reuse');
check(api_sync_decision([['id'=>2,'sha256'=>str_repeat('b',64),'original_name'=>'one.jpg']],$sha,'one.jpg')['decision']==='conflict','same name diff content');
check(api_sync_decision([
 ['id'=>2,'sha256'=>str_repeat('b',64),'original_name'=>'one.jpg'],
 ['id'=>9,'sha256'=>$sha,'original_name'=>'other.jpg']],$sha,'one.jpg')['id']===9,'checksum wins conflict');
echo "Sync preflight tests passed\n";
