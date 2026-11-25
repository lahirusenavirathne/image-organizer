<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
function assert_copy(bool $condition,string $message): void {
    if (!$condition) throw new RuntimeException('FAIL: '.$message);
    echo "PASS: $message\n";
}
assert_copy(editor_copy_filename('Yala leopard - final','webp')==='Yala leopard - final.webp','WebP save name');
assert_copy(editor_copy_filename('photo.jpeg','png')==='photo.png','Selected format supersedes typed extension');
assert_copy(editor_copy_filename('photo.webp','jpg')==='photo.jpg','JPEG generated with proper extension');
assert_copy(editor_copy_suggested_name('sunset.jpg')==='sunset-edited','Suggested name');
assert_copy(strlen(editor_copy_suggested_name(str_repeat('a',220).'.jpg'))<=180,'Suggested name bounded');
assert_copy(strlen(editor_copy_suggested_name(str_repeat('🐘',80).'.jpg'))<=180,'Suggested name UTF-8 byte bounded');
assert_copy(preg_match('//u',editor_copy_suggested_name(str_repeat('🐘',80).'.jpg'))===1,'Suggested name remains valid UTF-8');
foreach (['','  ','../path','bad/name','.', '..'] as $bad) {
    try {editor_copy_filename($bad,'webp');throw new RuntimeException('Unsafe name accepted: '.$bad);}
    catch (InvalidArgumentException) {assert_copy(true,'Invalid filename rejected: '.json_encode($bad));}
}
try {editor_copy_filename('photo','exe');throw new RuntimeException('Invalid format accepted');}
catch (InvalidArgumentException) {assert_copy(true,'Unsupported copy format rejected');}
// No DB or GD required for structural integration assertions.
$root=dirname(__DIR__);
$action=(string)file_get_contents($root.'/public/editor_action.php');
$editor=(string)file_get_contents($root.'/public/editor.php');
$js=(string)file_get_contents($root.'/public/assets/editor.js');
$helper=(string)file_get_contents($root.'/private/photo_editor.php');
assert_copy(str_contains($action,"'save_copy'") && str_contains($action,'editor_save_as_copy('),'Save-copy action routed to photo persistence');
assert_copy(str_contains((string)file_get_contents($root.'/private/images.php'),'bool $includeStorageName=false'),'Normal uploads do not expose private stored filename');
assert_copy(str_contains($action,"auth_require_user('editor')") && str_contains($action,'verify_csrf()'),'Editor permission and CSRF required');
assert_copy(str_contains($helper,'ingest_image($temp,') && str_contains($helper,'$db->beginTransaction()') && str_contains($helper,'$db->rollBack()'),'Copy uses transactional photo catalog ingest');
assert_copy(str_contains($helper,"'not analyzed'") && str_contains($helper,'$current[\'rights_status\']'),'AI reset and rights kept');
assert_copy(str_contains($editor,'id="editor-save-copy"') && str_contains($editor,'name="copy_name"'),'Photo studio includes copy control and filename');
assert_copy(str_contains($js,"send('save_copy',recipe())") && str_contains($js,"message.append(link)"),'Client offers link to saved copy');
assert_copy(str_contains($js,'exportSettingsValid(true)'),'Copy validates its filename separately from download');
echo "All save-as-copy structural checks passed\n";
