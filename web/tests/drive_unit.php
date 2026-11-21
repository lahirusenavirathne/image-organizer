<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/drive.php';

$cases=0;
function check(bool $condition,string $message): void {global $cases;$cases++;if(!$condition)throw new RuntimeException('FAILED: '.$message);}
check(drive_name('Sri Lanka Photos')==='Sri Lanka Photos','allow ordinary folder name');
foreach(['../etc','folder/subfolder','back\\slash','.', '..', "evil\0file",''] as $name) {
    try{drive_name($name);throw new RuntimeException('Unsafe name allowed: '.$name);}catch(RuntimeException $e){check(str_contains($e->getMessage(),'Invalid name'),'reject unsafe names');}
}
check(drive_id_or_root('')===null,'empty folder root');
check(drive_id_or_root(0)===null,'zero folder root');
check(drive_id_or_root('50')===50,'positive id accepted');
try{drive_photo_ids([1,2,3,4],2);throw new RuntimeException('Batches exceeded limit');}catch(RuntimeException $e){check(str_contains($e->getMessage(),'Select between'),'batch limit');}
check(drive_photo_ids([4,4,3])===[4,3],'deduplicate ids');
$rows=[
 ['id'=>1,'parent_id'=>null,'deleted_at'=>null],
 ['id'=>2,'parent_id'=>1,'deleted_at'=>null],
 ['id'=>3,'parent_id'=>2,'deleted_at'=>null],
 ['id'=>4,'parent_id'=>1,'deleted_at'=>'2026-11-20 01:00:00'],
 ['id'=>5,'parent_id'=>4,'deleted_at'=>null],
];
check(drive_descendants($rows,1)===[1,2,4,3,5],'all subfolders including deleted');
check(drive_descendants($rows,1,true)===[1,2,3],'active descendants exclude deleted subtree');
// A malformed cycle cannot make the algorithm loop indefinitely.
$cyclic=[['id'=>6,'parent_id'=>7,'deleted_at'=>null],['id'=>7,'parent_id'=>6,'deleted_at'=>null]];
check(drive_descendants($cyclic,6)===[6,7],'cycle bounded by seen ids');
echo "PASS: $cases file-manager unit assertions\n";
