<?php
declare(strict_types=1);
require_once dirname(__DIR__,3).'/private/api_tokens.php';
require_once dirname(__DIR__,3).'/private/api_v1_helpers.php';
require_once dirname(__DIR__,3).'/private/images.php';

header('Cache-Control: no-store');
header('Content-Type: application/json; charset=utf-8');
header('Vary: Authorization');
header('X-Content-Type-Options: nosniff');

try {
    if (!installed()) api_fail(503,'not_installed','Application is not installed');
    $db=pdo(); auth_migrate($db);drive_migrate($db);api_tokens_migrate($db);
    $user=api_authenticated_user($db);
    if ($user===null) api_fail(401,'unauthorized','A valid Bearer API token is required');
    if (!empty($user['rate_limited'])) api_fail(429,'rate_limit','Rate limit reached; retry after five minutes');
    $method=$_SERVER['REQUEST_METHOD']??'GET';
    if (!in_array($method,['GET','POST','PATCH','DELETE'],true)) {
        header('Allow: GET, POST, PATCH, DELETE');api_fail(405,'method_not_allowed','Method is not supported');
    }
    $resource=(string)($_GET['resource']??'me');
    $action=(string)($_GET['action']??'');
    $id=array_key_exists('id',$_GET)?api_photo_id():null;
    $scope=(string)$user['scope'];$role=(string)$user['role'];
    $needed=$method==='GET'?'read':'write';
    if ($method==='GET' && $resource==='files' && ($_GET['variant']??'thumb')==='original')$needed='write';
    if (!api_role_permitted($role,$scope,$needed))api_fail(403,'forbidden','Insufficient role or API token scope');

    if ($resource==='sync' && $method==='POST' && $action==='preflight') {
        // An explicit upload permission is required: read-only tokens cannot inspect
        // collision candidates or initiate sync operations.
        if (!api_role_permitted($role,$scope,'write'))api_fail(403,'forbidden','Write token required');
        $input=api_read_json_request();
        $sha=api_sync_sha($input['sha256']??null);
        $name=drive_name($input['name']??null,220);
        $size=$input['file_size']??null;
        if (!is_int($size) || $size<1 || $size>MAX_FILE_BYTES)
            throw new ApiBadRequest('file_size must be between 1 and 25 MiB');
        $folder=api_folder_filter($input['folder_id']??'root');
        drive_folder($db,$folder);
        $match=api_sync_match($db,$folder,$sha,$name);
        api_send(['data'=>['decision'=>$match['decision'],'remote_id'=>$match['id'],
            'remote_sha256'=>$match['sha256'],'folder_id'=>$folder]]);
    }
    if ($resource==='sync' && $method==='POST' && $action==='metadata_fill') {
        if (!api_role_permitted($role,$scope,'write'))
            api_fail(403,'forbidden','Write token required');
        $body=api_read_json_request();
        $photoId=int_id($body['photo_id']??null);
        $sha=api_sync_sha($body['sha256']??null);
        if (!isset($body['fields']) || !is_array($body['fields']) || array_is_list($body['fields']))
            throw new ApiBadRequest('fields must be a metadata object');
        foreach(array_keys($body) as $key)
            if (!in_array($key,['photo_id','sha256','fields'],true))throw new ApiBadRequest('Unsupported sync property');
        $result=api_metadata_fill($db,$photoId,$sha,$body['fields']);
        api_send(['data'=>$result]);
    }
    if ($resource==='me' && $method==='GET') {
        api_send(['data'=>['id'=>(int)$user['user_id'],'email'=>$user['email'],'role'=>$role,'scope'=>$scope,'api_version'=>'v1']]);
    }
    if ($resource==='folders') {
        if ($method==='GET' && $id===null) {
            $parent=api_folder_filter($_GET['parent_id']??'root');
            drive_folder($db,$parent);
            $sql='SELECT id,name,parent_id,created_at,updated_at FROM folders WHERE deleted_at IS NULL AND parent_id '.($parent===null?'IS NULL':'=?').' ORDER BY name LIMIT 500';
            $stmt=$db->prepare($sql);$stmt->execute($parent===null?[]:[$parent]);
            api_send(['data'=>$stmt->fetchAll(),'meta'=>['parent_id'=>$parent,'limit'=>500]]);
        }
        if ($method==='GET' && $id!==null) {
            $folder=drive_folder($db,$id);
            api_send(['data'=>['id'=>$folder['id'],'name'=>$folder['name'],'parent_id'=>$folder['parent_id'],
                'breadcrumbs'=>drive_folder_path($db,$id),'created_at'=>$folder['created_at']]]);
        }
        if ($method==='POST' && $id===null) {
            $body=api_read_json_request();
            if (!array_key_exists('name',$body))throw new ApiBadRequest('name is required');
            $parent=api_folder_filter($body['parent_id']??'root');
            $folderId=drive_create_folder($db,drive_name($body['name']),$parent,(int)$user['user_id']);
            api_send(['data'=>['id'=>$folderId]],201);
        }
        if ($method==='PATCH' && $id!==null) {
            $body=api_read_json_request();
            foreach(array_keys($body) as $key)if(!in_array($key,['name','parent_id'],true))throw new ApiBadRequest('Unsupported folder field');
            if (!$body)throw new ApiBadRequest('No folder changes supplied');
            $db->beginTransaction();
            try {
                if (array_key_exists('parent_id',$body))drive_move_folder($db,$id,api_folder_filter($body['parent_id']));
                if (array_key_exists('name',$body))drive_rename_folder($db,$id,drive_name($body['name']));
                $db->commit();
            } catch(Throwable $e){$db->rollBack();throw $e;}
            api_send(['data'=>['id'=>$id,'updated'=>true]]);
        }
        if ($method==='DELETE' && $id!==null) {
            $db->beginTransaction();try{$count=drive_trash_folder($db,$id);$db->commit();}catch(Throwable $e){$db->rollBack();throw $e;}
            api_send(['data'=>['id'=>$id,'trashed'=>true,'photos_affected'=>$count]]);
        }
        if ($method==='POST' && $id!==null && $action==='restore') {
            $db->beginTransaction();try{$count=drive_restore_folder($db,$id);$db->commit();}catch(Throwable $e){$db->rollBack();throw $e;}
            api_send(['data'=>['id'=>$id,'restored'=>true,'photos_restored'=>$count]]);
        }
        api_fail(405,'method_not_allowed','Unsupported folder operation');
    }
    if ($resource==='photos') {
        if ($method==='GET' && $id===null) {
            $page=api_page_number($_GET['page']??'1');$per=api_page_size($_GET['per_page']??'48');
            $trashed=($_GET['trash']??'0')==='1';
            if ($trashed && !api_role_permitted($role,$scope,'write'))api_fail(403,'forbidden','Trash requires editor permissions');
            $conditions=[$trashed?'p.deleted_at IS NOT NULL':'p.deleted_at IS NULL'];$params=[];
            if(isset($_GET['folder_id'])) {
                $folder=api_folder_filter($_GET['folder_id']);
                $conditions[]=$folder===null?'p.folder_id IS NULL':'p.folder_id=?';
                if ($folder!==null)$params[]=$folder;
            }
            $q=clean_text($_GET['q']??'',100);
            if ($q!=='') {
                $like='%'.str_replace(['\\','%','_'],['\\\\','\\%','\\_'],$q).'%';
                $conditions[]="(p.original_name LIKE ? OR p.location LIKE ? OR p.attraction LIKE ? OR p.activities LIKE ?)";
                array_push($params,$like,$like,$like,$like);
            }
            $where=implode(' AND ',$conditions);
            $count=$db->prepare('SELECT COUNT(*) FROM photos p WHERE '.$where);$count->execute($params);$total=(int)$count->fetchColumn();
            $pages=max(1,(int)ceil($total/$per));$page=min($page,$pages);
            $cols='id,original_name,sha256,mime,file_size,width,height,folder_id,camera,taken_at,location,attraction,activities,source_folder,source_url,photographer,copyright_text,license,rights_status,ai_status,ai_note,created_at,updated_at';
            $stmt=$db->prepare("SELECT $cols FROM photos p WHERE $where ORDER BY p.id DESC LIMIT $per OFFSET ".(($page-1)*$per));
            $stmt->execute($params);
            api_send(['data'=>$stmt->fetchAll(),'meta'=>['page'=>$page,'per_page'=>$per,'pages'=>$pages,'total'=>$total]]);
        }
        if ($method==='GET' && $id!==null) {
            $photo=drive_photo($db,$id);
            api_send(['data'=>api_photo_public($photo)]);
        }
        if ($method==='POST' && $id===null) {
            $file=$_FILES['photo']??null;
            if (!$file || ($file['error']??UPLOAD_ERR_NO_FILE)!==UPLOAD_ERR_OK || !is_uploaded_file($file['tmp_name']??''))
                throw new ApiBadRequest('Multipart file photo is required; check PHP upload limits');
            $folder=api_folder_filter($_POST['folder_id']??'root');
            $dest=drive_upload_destination($db,$folder,(string)($_POST['relative_path']??''),(int)$user['user_id']);
            // Only desktop sync sends a sha256 field. Legacy browser uploads keep
            // their original behavior. The hash is verified against received bytes.
            $expected=$_POST['sha256']??null;
            if ($expected!==null) {
                $hash=api_sync_sha($expected);
                if (!hash_equals($hash,hash_file('sha256',$file['tmp_name'])))
                    throw new ApiBadRequest('Upload SHA-256 does not match the received file');
                $display=drive_name(safe_basename((string)$file['name']),220);
                // Serialize uploads within a destination folder so a timeout/retry
                // cannot race a concurrent request into inserting duplicate records.
                $lockName='glpm_sync_'.hash('sha256','folder:'.($dest??'root'));
                $lockQuery=$db->prepare('SELECT GET_LOCK(?, 10)');
                $lockQuery->execute([$lockName]);
                if ((int)$lockQuery->fetchColumn()!==1)
                    api_fail(503,'busy','Upload destination is busy; retry later');
                try {
                    $match=api_sync_match($db,$dest,$hash,$display);
                    if ($match['decision']==='upload') {
                        $record=ingest_image($file['tmp_name'],(string)$file['name'],'Desktop sync upload',true);
                        $db->prepare('UPDATE photos SET folder_id=? WHERE id=?')->execute([$dest,$record['id']]);
                    }
                } finally {
                    // Always release the advisory lock before sending a response.
                    $db->prepare('SELECT RELEASE_LOCK(?)')->execute([$lockName]);
                }
                if ($match['decision']==='duplicate')
                    api_send(['data'=>['id'=>$match['id'],'decision'=>'duplicate','folder_id'=>$dest]],200);
                if ($match['decision']==='conflict')
                    api_fail(409,'name_conflict','A different photograph already has this name in the target folder.');
                api_send(['data'=>['id'=>$record['id'],'name'=>$record['name'],'folder_id'=>$dest,'decision'=>'uploaded']],201);
            }
            $record=ingest_image($file['tmp_name'],(string)$file['name'],'API upload',true);
            $db->prepare('UPDATE photos SET folder_id=? WHERE id=?')->execute([$dest,$record['id']]);
            api_send(['data'=>['id'=>$record['id'],'name'=>$record['name'],'folder_id'=>$dest]],201);
        }
        if ($method==='PATCH' && $id!==null) {
            drive_photo($db,$id);
            $body=api_read_json_request();
            $fields=['original_name'=>220,'location'=>150,'attraction'=>190,'activities'=>500,'source_folder'=>500,
                    'source_url'=>1000,'photographer'=>255,'copyright_text'=>1000,'license'=>255];
            $allowed=array_merge(array_keys($fields),['rights_status','folder_id']);
            foreach(array_keys($body) as $key)if(!in_array($key,$allowed,true))throw new ApiBadRequest('Unsupported photo field');
            if (!$body)throw new ApiBadRequest('No changes supplied');
            $db->beginTransaction();
            try {
                $values=[];$set=[];
                foreach($fields as $key=>$max) if (array_key_exists($key,$body)) {
                    if (!is_string($body[$key]))throw new ApiBadRequest($key.' must be a string');
                    $value=$key==='original_name'?drive_name($body[$key],$max):clean_text($body[$key],$max);
                    if ($key==='source_url' && $value!=='' && (!filter_var($value,FILTER_VALIDATE_URL) || !in_array(strtolower(parse_url($value,PHP_URL_SCHEME)),['https','http'],true)))
                        throw new ApiBadRequest('source_url must be an HTTP(S) URL');
                    $set[]="$key=?";$values[]=$value;
                }
                if (array_key_exists('rights_status',$body)) {
                    $rights=$body['rights_status'];
                    if (!in_array($rights,['Unknown','Verified','Permission required'],true))throw new ApiBadRequest('Invalid rights_status');
                    $set[]='rights_status=?';$values[]=$rights;
                }
                if (array_key_exists('folder_id',$body)) {
                    $folder=api_folder_filter($body['folder_id']);drive_folder($db,$folder);
                    $set[]='folder_id=?';$values[]=$folder;
                }
                if (count($set)>0) {
                    if (array_intersect(array_keys($body),['location','attraction','activities','rights_status'])) $set[]="ai_status='reviewed'";
                    $stmt=$db->prepare('UPDATE photos SET '.implode(',',$set).' WHERE id=? AND deleted_at IS NULL');$values[]=$id;$stmt->execute($values);
                }
                $db->commit();
            } catch(Throwable $e){$db->rollBack();throw $e;}
            api_send(['data'=>['id'=>$id,'updated'=>true]]);
        }
        if ($method==='DELETE' && $id!==null) {
            drive_trash_photos($db,[$id]);api_send(['data'=>['id'=>$id,'trashed'=>true]]);
        }
        if ($method==='POST' && $id!==null && $action==='restore') {
            drive_restore_photo($db,$id);api_send(['data'=>['id'=>$id,'restored'=>true]]);
        }
        if ($method==='POST' && $id!==null && $action==='copy') {
            $body=api_read_json_request();$folder=api_folder_filter($body['folder_id']??'root');drive_folder($db,$folder);
            $src=drive_photo($db,$id);$copy=drive_copy_photo($db,$src,$folder);
            api_send(['data'=>['id'=>$copy,'copied_from'=>$id]],201);
        }
        api_fail(405,'method_not_allowed','Unsupported photo operation');
    }
    if ($resource==='files' && $method==='GET' && $id!==null) {
        $variant=(string)($_GET['variant']??'thumb');
        if(!in_array($variant,['thumb','original'],true))throw new ApiBadRequest('Invalid file variant');
        $photo=drive_photo($db,$id);
        $path=photo_path($photo,$variant==='thumb');
        if(!is_file($path))api_fail(404,'not_found','File is unavailable');
        // Binary is returned only after successful Bearer auth. Never redirect to a public disk path.
        header('Content-Type: '.($variant==='thumb'?'image/jpeg':$photo['mime']));
        header('Content-Length: '.(string)filesize($path));
        header('Cache-Control: private, no-store');
        $name=$variant==='thumb'?'thumbnail.jpg':api_safe_filename($photo['original_name']);
        header('Content-Disposition: attachment; filename="'.$name.'"');
        readfile($path);exit;
    }
    api_fail(404,'not_found','Unknown API resource');
} catch (ApiBadRequest $e) {
    api_fail(422,'validation_error',$e->getMessage());
} catch (PDOException $e) {
    error_log('GLPM API v1 database operation failed');
    api_fail(503,'database_unavailable','Database temporarily unavailable');
} catch (Throwable $e) {
    // Do not leak disk paths or credentials through error messages.
    error_log('GLPM API v1 operation failed: '.get_class($e));
    api_fail(400,'request_failed','Request could not be completed; check input or resource state');
}
