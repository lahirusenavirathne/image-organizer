<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/images.php';
function it(bool $condition,string $description): void {
    if(!$condition){fwrite(STDERR,"FAIL: $description\n");exit(1);}echo "PASS: $description\n";
}
it(hamming_hex('0000000000000000','0000000000000000')===0,'Identical visual hashes');
it(hamming_hex('0000000000000000','ffffffffffffffff')===64,'Opposite visual hashes');
it(hamming_hex('ffff000000000000','fffe000000000000')===1,'Single-bit visual difference');
it(hamming_hex('not valid','0000000000000000')===65,'Invalid hash rejected');
it(safe_basename('../../../../photo.JPG')==='photo.JPG','Source filename sanitized');
it(safe_basename('..\\..\\wildlife.jpg')==='wildlife.jpg','Windows path sanitized');
it(clean_text('  Sri Lanka  ')==='Sri Lanka','Text normalization');
it(!installed() || is_file(private_path('config.php')),'Installation check');
it(is_file(dirname(__DIR__).'/public/assets/app.js'),'Browser application packaged');
it(is_file(dirname(__DIR__).'/private/schema.sql'),'MySQL schema packaged');
echo "Smoke checks passed (no MySQL/GD required for these tests).\n";
$probe=['stored_name'=>str_repeat('a',40).'.jpg'];
it(str_ends_with(photo_path($probe),'originals/'.str_repeat('a',40).'.jpg'),'Private originals path');
try { photo_path(['stored_name'=>'../oops.jpg']); it(false,'Path traversal rejected'); } catch(RuntimeException) { it(true,'Path traversal rejected'); }

it(color_distance('ffffff','ffffff')===0.0,'Identical average colors');
it(color_distance('000000','ffffff')>300,'Different average colors excluded');
