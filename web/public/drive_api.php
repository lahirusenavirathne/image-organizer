<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/drive.php';
require_once dirname(__DIR__).'/private/images.php';

try {
    if(!installed())respond(['error'=>'Application not installed'],503);
    $user=auth_require_user();$db=pdo();drive_migrate($db);
    $action=(string)($_GET['action']??$_POST['action']??'list');
    if(($_SERVER['REQUEST_METHOD']??'GET')==='GET') {
        if($action==='list') {
            $view=(string)($_GET['view']??'drive');
            if(!in_array($view,['drive','all','recent','trash','review'],true))throw new RuntimeException('Unsupported view');
            if($view==='trash')auth_require_user('editor');
            $folder=drive_id_or_root($_GET['folder']??null);
            if($view==='drive')drive_folder($db,$folder);
            $q=clean_text($_GET['q']??'',100);
            $sort=(string)($_GET['sort']??'newest');
            if(!in_array($sort,['newest','oldest','name','size'],true))$sort='newest';
            $sortBy=match($sort){'oldest'=>'p.created_at ASC,p.id ASC','name'=>'p.original_name ASC,p.id DESC','size'=>'p.file_size DESC,p.id DESC',default=>'p.created_at DESC,p.id DESC'};
            $page=max(1,min(100000,(int)($_GET['page']??1)));$limit=48;
            $filter=[];$params=[];
            $filter[]=$view==='trash'?'p.deleted_at IS NOT NULL':'p.deleted_at IS NULL';
            if($view==='trash'){
                $filter[]='NOT EXISTS (SELECT 1 FROM folders ft WHERE ft.id=p.folder_id AND ft.deleted_at IS NOT NULL AND ft.trash_batch=p.trash_batch)';
            } elseif($view==='review')$filter[]="p.ai_status='suggested'";
            elseif($view==='drive' && $q==='') {
                $filter[]=$folder===null?'p.folder_id IS NULL':'p.folder_id=?';
                if($folder!==null)$params[]=$folder;
            }
            if($q!==''){
                $like='%'.str_replace(['\\','%','_'],['\\\\','\\%','\\_'],$q).'%';
                $filter[]="(p.original_name LIKE ? ESCAPE '\\\\' OR p.location LIKE ? ESCAPE '\\\\' OR p.attraction LIKE ? ESCAPE '\\\\' OR p.activities LIKE ? ESCAPE '\\\\')";
                $params=array_merge($params,[$like,$like,$like,$like]);
            }
            $location=clean_text($_GET['location']??'',150);
            if($location!==''){$filter[]='p.location=?';$params[]=$location;}
            $activity=clean_text($_GET['activity']??'',100);
            if($activity!==''){$filter[]='p.activities LIKE ?';$params[]='%'.$activity.'%';}
            $rights=clean_text($_GET['rights']??'',32);
            if(in_array($rights,['Unknown','Verified','Permission required'],true)){$filter[]='p.rights_status=?';$params[]=$rights;}
            $where=implode(' AND ',$filter);
            $count=$db->prepare('SELECT COUNT(*) FROM photos p WHERE '.$where);$count->execute($params);$total=(int)$count->fetchColumn();
            $page=min($page,max(1,(int)ceil($total/$limit)));
            $rows=$db->prepare('SELECT p.id,p.original_name,p.mime,p.width,p.height,p.file_size,p.folder_id,p.camera,p.taken_at,p.sha256,p.updated_at,p.location,p.attraction,p.activities,p.rights_status,p.photographer,p.source_folder,p.source_url,p.copyright_text,p.license,p.ai_status,p.ai_note,p.created_at,p.deleted_at FROM photos p WHERE '.$where.' ORDER BY '.$sortBy.' LIMIT '.$limit.' OFFSET '.(($page-1)*$limit));
            $rows->execute($params);
            $folders=[];
            if($view==='drive' || $view==='trash'){
                $parts=[];$values=[];
                if($view==='trash') {
                    $parts[]='f.deleted_at IS NOT NULL';
                    $parts[]='NOT EXISTS (SELECT 1 FROM folders ft WHERE ft.id=f.parent_id AND ft.deleted_at IS NOT NULL AND ft.trash_batch=f.trash_batch)';
                } else {
                    $parts[]='f.deleted_at IS NULL';
                    if($q===''){$parts[]=$folder===null?'f.parent_id IS NULL':'f.parent_id=?';if($folder!==null)$values[]=$folder;}
                }
                if($q!==''){$parts[]='f.name LIKE ?';$values[]='%'.str_replace(['%','_'],['\\%','\\_'],$q).'%';}
                $sql='SELECT f.id,f.name,f.parent_id,f.created_at,f.deleted_at FROM folders f WHERE '.implode(' AND ',$parts).' ORDER BY f.name ASC LIMIT 300';
                $fs=$db->prepare($sql);$fs->execute($values);$folders=$fs->fetchAll();
            }
            $crumbs=$view==='drive'?drive_folder_path($db,$folder):[];
            $locations=$db->query("SELECT DISTINCT location FROM photos WHERE deleted_at IS NULL AND location<>'' ORDER BY location LIMIT 300")->fetchAll(PDO::FETCH_COLUMN);
            respond(['photos'=>$rows->fetchAll(),'folders'=>$folders,'locations'=>$locations,'folder_options'=>drive_folder_options($db),
                'breadcrumbs'=>$crumbs,'folder'=>$folder,'page'=>$page,'pages'=>max(1,(int)ceil($total/$limit)),
                'total'=>$total,'view'=>$view]);
        }
        respond(['error'=>'Unknown file-manager read action'],404);
    }
    method_post();verify_csrf();
    auth_require_user('editor');
    $folder=drive_id_or_root($_POST['folder']??null);
    if($action==='create_folder'){
        $id=drive_create_folder($db,(string)($_POST['name']??''),$folder,(int)$user['id']);
        respond(['success'=>true,'id'=>$id]);
    }
    if($action==='rename_folder'){
        drive_rename_folder($db,int_id($_POST['id']??null),(string)($_POST['name']??''));respond(['success'=>true]);
    }
    if($action==='move_folder'){
        drive_move_folder($db,int_id($_POST['id']??null),$folder);respond(['success'=>true]);
    }
    if($action==='rename_photo'){
        $id=int_id($_POST['id']??null);drive_photo($db,$id);
        $name=drive_name($_POST['name']??null,220);
        $st=$db->prepare('UPDATE photos SET original_name=? WHERE id=? AND deleted_at IS NULL');$st->execute([$name,$id]);respond(['success'=>true]);
    }
    if($action==='move_photos'){
        $ids=drive_photo_ids(json_decode((string)($_POST['ids']??''),true));
        $db->beginTransaction();try{$moved=drive_bulk_move($db,$ids,$folder);$db->commit();}catch(Throwable $e){$db->rollBack();throw $e;}
        respond(['success'=>true,'moved'=>$moved]);
    }
    if($action==='copy_photos'){
        $ids=drive_photo_ids(json_decode((string)($_POST['ids']??''),true),DRIVE_MAX_COPY);
        drive_folder($db,$folder);$copied=0;
        foreach($ids as $id){$src=drive_photo($db,$id);drive_copy_photo($db,$src,$folder);$copied++;}
        respond(['success'=>true,'copied'=>$copied]);
    }
    if($action==='trash_photos'){
        $ids=drive_photo_ids(json_decode((string)($_POST['ids']??''),true));
        $db->beginTransaction();try{$done=drive_trash_photos($db,$ids);$db->commit();}catch(Throwable $e){$db->rollBack();throw $e;}
        respond(['success'=>true,'trashed'=>$done]);
    }
    if($action==='trash_folder'){
        $id=int_id($_POST['id']??null);
        $db->beginTransaction();try{$done=drive_trash_folder($db,$id);$db->commit();}catch(Throwable $e){$db->rollBack();throw $e;}
        respond(['success'=>true,'trashed_folder'=>$id,'photos_affected'=>$done]);
    }
    if($action==='restore_photo'){
        $id=int_id($_POST['id']??null);drive_restore_photo($db,$id);respond(['success'=>true]);
    }
    if($action==='restore_folder'){
        $id=int_id($_POST['id']??null);
        $db->beginTransaction();try{$done=drive_restore_folder($db,$id);$db->commit();}catch(Throwable $e){$db->rollBack();throw $e;}
        respond(['success'=>true,'photos_restored'=>$done]);
    }
    if($action==='purge_photo' || $action==='purge_folder'){
        auth_require_user('admin');
        if(($_POST['confirm']??'')!=='DELETE PERMANENTLY')throw new RuntimeException('Explicit permanent deletion confirmation required');
        $id=int_id($_POST['id']??null);
        $db->beginTransaction();
        try{$paths=$action==='purge_photo'?drive_permanent_photo($db,$id):drive_purge_folder($db,$id);$db->commit();}
        catch(Throwable $e){$db->rollBack();throw $e;}
        $failed=drive_unlink_paths($paths);
        respond(['success'=>true,'cleanup_failed'=>$failed]);
    }
    respond(['error'=>'Unknown file-manager action'],404);
} catch(Throwable $e) {
    $status=http_response_code();
    error_log('GLPM Drive: '.get_class($e).': '.$e->getMessage());
    respond(['error'=>$e instanceof PDOException?'Database operation failed; check the PHP error log.':$e->getMessage()],$status>=400?$status:400);
}
