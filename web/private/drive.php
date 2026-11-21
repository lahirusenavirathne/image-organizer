<?php
declare(strict_types=1);
require_once __DIR__.'/auth.php';

/** Google Drive-style photo organization. Physical originals stay under private/originals. */
const DRIVE_MAX_BULK = 50;
const DRIVE_MAX_COPY = 12;
const DRIVE_MAX_PURGE = 25;

function drive_migrate(PDO $db): void {
    if (is_file(private_path('drive-v3-ready'))) return;
    $lock = fopen(private_path('drive-v3-migrate.lock'), 'c');
    if (!$lock || !flock($lock, LOCK_EX)) throw new RuntimeException('Cannot lock file-manager upgrade');
    try {
        if (is_file(private_path('drive-v3-ready'))) return;
        $db->exec("CREATE TABLE IF NOT EXISTS folders (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(190) NOT NULL,
            parent_id BIGINT UNSIGNED NULL,
            created_by BIGINT UNSIGNED NULL,
            deleted_at DATETIME NULL,
            trash_batch CHAR(32) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_folder_parent (parent_id),
            KEY idx_folder_deleted (deleted_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
        $columns=$db->query('SHOW COLUMNS FROM photos')->fetchAll(PDO::FETCH_COLUMN);
        if (!in_array('folder_id',$columns,true)) $db->exec('ALTER TABLE photos ADD COLUMN folder_id BIGINT UNSIGNED NULL DEFAULT NULL');
        if (!in_array('deleted_at',$columns,true)) $db->exec('ALTER TABLE photos ADD COLUMN deleted_at DATETIME NULL');
        if (!in_array('trash_batch',$columns,true)) $db->exec('ALTER TABLE photos ADD COLUMN trash_batch CHAR(32) NULL');
        $index=$db->query('SHOW INDEX FROM photos')->fetchAll(PDO::FETCH_ASSOC);
        $names=array_column($index,'Key_name');
        if (!in_array('idx_photo_folder_live',$names,true)) $db->exec('CREATE INDEX idx_photo_folder_live ON photos(folder_id,deleted_at)');
        $temp=private_path('drive-v3-ready.tmp');
        if (file_put_contents($temp,"ready\n",LOCK_EX)===false || !rename($temp,private_path('drive-v3-ready')))
            throw new RuntimeException('Unable to finalize file-manager migration');
        @chmod(private_path('drive-v3-ready'),0600);
    } finally {flock($lock,LOCK_UN);fclose($lock);}
}
function drive_name(mixed $value, int $max=190): string {
    if (!is_string($value)) throw new RuntimeException('A name is required');
    $name=trim($value);
    if ($name==='' || $name==='.' || $name==='..' || strlen($name)>$max ||
        preg_match('/[\\x00-\\x1f\\x7f\\/\\\\]/u',$name)) throw new RuntimeException('Invalid name: no slashes, control characters or empty names');
    return $name;
}
function drive_id_or_root(mixed $id): ?int {
    if ($id===null || $id==='' || $id==='0' || $id===0) return null;
    return int_id($id);
}
function drive_folder(PDO $db, ?int $id, bool $allowDeleted=false): ?array {
    if ($id===null) return null;
    $q=$db->prepare('SELECT * FROM folders WHERE id=? LIMIT 1');$q->execute([$id]);$row=$q->fetch();
    if (!$row || (!$allowDeleted && $row['deleted_at']!==null)) throw new RuntimeException('Folder does not exist or is in Trash');
    return $row;
}
function drive_folder_children(PDO $db): array {
    return $db->query('SELECT id,parent_id,deleted_at,trash_batch FROM folders ORDER BY id')->fetchAll();
}
/** Iterative, bounded traversal; failed cycle validation never modifies the database. */
function drive_descendants(array $rows,int $root,bool $onlyLive=false): array {
    $byParent=[];
    foreach($rows as $row) {
        if($row['parent_id']===null || ($onlyLive && $row['deleted_at']!==null))continue;
        $parent=(int)$row['parent_id'];
        $byParent[$parent][]=(int)$row['id'];
    }
    $seen=[$root=>true];$queue=[$root];$result=[];
    for($i=0;$i<count($queue);$i++) {
        $node=$queue[$i];$result[]=$node;
        foreach($byParent[$node]??[] as $id)if(!isset($seen[$id])){$seen[$id]=true;$queue[]=$id;}
        if(count($result)>25000)throw new RuntimeException('Folder tree is too large for one operation');
    }
    return $result;
}
function drive_folder_name_taken(PDO $db,string $name,?int $parent,?int $exclude=null): bool {
    $sql='SELECT id FROM folders WHERE deleted_at IS NULL AND name=? AND parent_id '.($parent===null?'IS NULL':'=?');
    $params=[$name];if($parent!==null)$params[]=$parent;
    if($exclude!==null){$sql.=' AND id<>?';$params[]=$exclude;}
    $sql.=' LIMIT 1';$s=$db->prepare($sql);$s->execute($params);return (bool)$s->fetch();
}
function drive_create_folder(PDO $db,string $name,?int $parent,int $userId): int {
    drive_folder($db,$parent);
    $name=drive_name($name);
    if(drive_folder_name_taken($db,$name,$parent))throw new RuntimeException('A folder with this name already exists here');
    $s=$db->prepare('INSERT INTO folders(name,parent_id,created_by) VALUES(?,?,?)');$s->execute([$name,$parent,$userId]);
    return (int)$db->lastInsertId();
}
function drive_folder_path(PDO $db,?int $folder): array {
    $crumbs=[];$seen=[];
    while($folder!==null) {
        if(isset($seen[$folder]) || count($seen)>30)throw new RuntimeException('Invalid folder hierarchy');
        $seen[$folder]=true;$row=drive_folder($db,$folder);
        $crumbs[]=['id'=>(int)$row['id'],'name'=>$row['name']];$folder=$row['parent_id']!==null?(int)$row['parent_id']:null;
    }
    return array_reverse($crumbs);
}
function drive_folder_options(PDO $db): array {
    return $db->query('SELECT id,name,parent_id FROM folders WHERE deleted_at IS NULL ORDER BY name LIMIT 10000')->fetchAll();
}
function drive_photo(PDO $db,int $id,bool $trashed=false): array {
    $s=$db->prepare('SELECT * FROM photos WHERE id=? AND deleted_at IS '.($trashed?'NOT NULL':'NULL').' LIMIT 1');
    $s->execute([$id]);$row=$s->fetch();if(!$row)throw new RuntimeException('Photo not found in this location');return $row;
}
function drive_photo_ids(mixed $ids,int $limit=DRIVE_MAX_BULK): array {
    if(!is_array($ids) || count($ids)<1 || count($ids)>$limit)throw new RuntimeException('Select between 1 and '.$limit.' photographs');
    $out=[];foreach($ids as $id)$out[]=int_id($id);
    return array_values(array_unique($out));
}
function drive_sql_ids(array $ids): string {return implode(',',array_fill(0,count($ids),'?'));}
/** Organize an upload into an existing folder, or recreate a safely validated browser folder path. */
function drive_upload_destination(PDO $db,?int $folder,string $relative,int $userId): ?int {
    drive_folder($db,$folder);
    if($relative==='')return $folder;
    $parts=explode('/',$relative);
    if(count($parts)>9 || count($parts)<2)throw new RuntimeException('Invalid uploaded folder structure');
    array_pop($parts); // final component is the file name, already validated independently.
    foreach($parts as $part) {
        $part=drive_name($part);
        $stmt=$db->prepare('SELECT id FROM folders WHERE parent_id '.($folder===null?'IS NULL':'=?').' AND name=? AND deleted_at IS NULL LIMIT 1');
        $stmt->execute($folder===null?[$part]:[$folder,$part]);$existing=$stmt->fetchColumn();
        $folder=$existing ? (int)$existing : drive_create_folder($db,$part,$folder,$userId);
    }
    return $folder;
}
function drive_rename_folder(PDO $db,int $id,string $name): void {
    $row=drive_folder($db,$id);$parent=$row['parent_id']===null?null:(int)$row['parent_id'];
    $name=drive_name($name);
    if(drive_folder_name_taken($db,$name,$parent,$id))throw new RuntimeException('That folder name is already in use');
    $s=$db->prepare('UPDATE folders SET name=? WHERE id=? AND deleted_at IS NULL');$s->execute([$name,$id]);
}
function drive_move_folder(PDO $db,int $id,?int $target): void {
    drive_folder($db,$id);drive_folder($db,$target);
    $ids=drive_descendants(drive_folder_children($db),$id);
    if($target!==null && in_array($target,$ids,true))throw new RuntimeException('Cannot move a folder inside itself or a descendant');
    $row=drive_folder($db,$id);
    if(drive_folder_name_taken($db,$row['name'],$target,$id))throw new RuntimeException('A folder with the same name already exists in the destination');
    $s=$db->prepare('UPDATE folders SET parent_id=? WHERE id=?');$s->execute([$target,$id]);
}
function drive_bulk_move(PDO $db,array $ids,?int $destination): int {
    drive_folder($db,$destination);$count=0;$s=$db->prepare('UPDATE photos SET folder_id=? WHERE id=? AND deleted_at IS NULL');
    foreach($ids as $id){drive_photo($db,$id);$s->execute([$destination,$id]);$count+=$s->rowCount();}
    return $count;
}
function drive_copy_photo(PDO $db,array $photo,?int $folder): int {
    $stored=bin2hex(random_bytes(20)).'.'.mime_extension($photo['mime']);
    $new=$photo;$new['stored_name']=$stored;
    if(!copy(photo_path($photo),photo_path($new)))throw new RuntimeException('Could not copy original file');
    if(!copy(photo_path($photo,true),photo_path($new,true))){@unlink(photo_path($new));throw new RuntimeException('Could not copy thumbnail');}
    try {
        $fields=['stored_name','original_name','sha256','dhash','color_sig','mime','file_size','width','height',
            'camera','taken_at','location','attraction','activities','source_folder','source_url','photographer',
            'copyright_text','license','rights_status','ai_status','ai_note'];
        $params=array_map(fn($key)=>$key==='stored_name'?$stored:($key==='original_name'?substr('Copy of '.$photo[$key],0,220):$photo[$key]),$fields);
        $fields[]='folder_id';$params[]=$folder;
        $stmt=$db->prepare('INSERT INTO photos ('.implode(',',$fields).') VALUES ('.drive_sql_ids($fields).')');
        $stmt->execute($params);return (int)$db->lastInsertId();
    } catch(Throwable $e) {@unlink(photo_path($new));@unlink(photo_path($new,true));throw $e;}
}
function drive_trash_photos(PDO $db,array $ids): int {
    $s=$db->prepare('UPDATE photos SET deleted_at=UTC_TIMESTAMP(),trash_batch=? WHERE id=? AND deleted_at IS NULL');
    $count=0;foreach($ids as $id){drive_photo($db,$id);$s->execute([bin2hex(random_bytes(16)),$id]);$count+=$s->rowCount();}return $count;
}
function drive_trash_folder(PDO $db,int $root): int {
    drive_folder($db,$root);$ids=drive_descendants(drive_folder_children($db),$root,true);
    $batch=bin2hex(random_bytes(16));$places=drive_sql_ids($ids);
    $stmt=$db->prepare("UPDATE photos SET deleted_at=UTC_TIMESTAMP(),trash_batch=? WHERE deleted_at IS NULL AND folder_id IN ($places)");
    $stmt->execute([$batch,...$ids]);$count=$stmt->rowCount();
    $stmt=$db->prepare("UPDATE folders SET deleted_at=UTC_TIMESTAMP(),trash_batch=? WHERE deleted_at IS NULL AND id IN ($places)");$stmt->execute([$batch,...$ids]);
    return $count;
}
function drive_restore_photo(PDO $db,int $id): void {
    $photo=drive_photo($db,$id,true);$folder=$photo['folder_id']===null?null:(int)$photo['folder_id'];
    try{drive_folder($db,$folder);}catch(RuntimeException){$folder=null;}
    $stmt=$db->prepare('UPDATE photos SET deleted_at=NULL,trash_batch=NULL,folder_id=? WHERE id=?');$stmt->execute([$folder,$id]);
}
function drive_restore_folder(PDO $db,int $id): int {
    $root=drive_folder($db,$id,true);
    if($root['deleted_at']===null)throw new RuntimeException('Folder is not in Trash');
    $batch=(string)$root['trash_batch'];
    if(!preg_match('/\A[a-f0-9]{32}\z/',$batch))throw new RuntimeException('Invalid Trash group');
    $parent=$root['parent_id']!==null?(int)$root['parent_id']:null;
    try{drive_folder($db,$parent);}catch(RuntimeException){$parent=null;}
    $name=$root['name'];
    if(drive_folder_name_taken($db,$name,$parent)){
        $name=substr($name,0,160).' (restored '.bin2hex(random_bytes(4)).')';
    }
    $s=$db->prepare('UPDATE folders SET parent_id=?,name=? WHERE id=?');$s->execute([$parent,$name,$id]);
    $s=$db->prepare('UPDATE folders SET deleted_at=NULL,trash_batch=NULL WHERE trash_batch=?');$s->execute([$batch]);
    $s=$db->prepare('UPDATE photos SET deleted_at=NULL,trash_batch=NULL WHERE trash_batch=?');$s->execute([$batch]);
    return $s->rowCount();
}
function drive_permanent_photo(PDO $db,int $id): array {
    $row=drive_photo($db,$id,true);
    $s=$db->prepare('DELETE FROM photos WHERE id=? AND deleted_at IS NOT NULL');$s->execute([$id]);
    return [photo_path($row),photo_path($row,true)];
}
function drive_purge_folder(PDO $db,int $id): array {
    $root=drive_folder($db,$id,true);
    if($root['deleted_at']===null)throw new RuntimeException('Folder is not in Trash');
    $all=drive_descendants(drive_folder_children($db),$id);
    if(count($all)>DRIVE_MAX_PURGE)throw new RuntimeException('Folder has too many subfolders for online permanent deletion; use smaller batches');
    $p=drive_sql_ids($all);
    $stmt=$db->prepare("SELECT * FROM photos WHERE folder_id IN ($p) LIMIT ".(DRIVE_MAX_PURGE+1));$stmt->execute($all);$photos=$stmt->fetchAll();
    if(count($photos)>DRIVE_MAX_PURGE)throw new RuntimeException('Folder has too many images for online permanent deletion; delete in smaller batches');
    foreach($photos as $photo)if($photo['deleted_at']===null)throw new RuntimeException('Folder contains active photos');
    $paths=[];foreach($photos as $photo){$paths[] = photo_path($photo);$paths[]=photo_path($photo,true);}
    $stmt=$db->prepare("DELETE FROM photos WHERE folder_id IN ($p)");$stmt->execute($all);
    foreach(array_reverse($all) as $fid){$stmt=$db->prepare('DELETE FROM folders WHERE id=? AND deleted_at IS NOT NULL');$stmt->execute([$fid]);}
    return $paths;
}
function drive_unlink_paths(array $paths): int {
    $fail=0;foreach($paths as $p)if(is_file($p)&&!unlink($p)){$fail++;error_log('GLPM unable to unlink orphaned file in private storage');}
    return $fail;
}
